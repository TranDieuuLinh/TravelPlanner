#!/usr/bin/env python3
"""Add conservative searchable aliases for reviewed non-Latin place names."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal  # noqa: E402
from app.modules.knowledge_graph.model import (  # noqa: E402
    KnowledgeAlias,
    KnowledgeEntity,
    KnowledgeProperty,
)
from app.modules.knowledge_graph.text import normalize_knowledge_text  # noqa: E402


PROVIDER = "codex_curated_alias_backfill"


@dataclass(frozen=True)
class AliasSpec:
    canonical_name: str
    alias: str
    language: str = "en"
    confidence: float = 0.9


# These are reviewable transliterations/translations, not verified provider names.
ALIAS_SPECS = (
    AliasSpec("황진이 가라오케", "Hwang Jini Karaoke"),
    AliasSpec("ハノイレディ", "Hanoi Lady"),
    AliasSpec("비너스가라오케", "Venus Karaoke"),
    AliasSpec("琉璃餐厅【淄博烧烤】", "Liuli Restaurant Zibo BBQ", confidence=0.85),
    AliasSpec("松庵日本料理レストラン", "Shoan Japanese Restaurant", confidence=0.85),
    AliasSpec("화정족발 호떠이점 (한식, 중식)", "Hwajeong Jokbal West Lake Branch"),
    AliasSpec("명월(明月) 하노이, 한식당", "Myeongwol Hanoi Korean Restaurant"),
    AliasSpec("하노이 주말 야시장 입구", "Hanoi Weekend Night Market Entrance"),
    AliasSpec("하노이하늘숲교회", "Hanoi Haneul Sup Church", confidence=0.85),
    AliasSpec("하노이 한인교회", "Hanoi Korean Church"),
    AliasSpec("하노이 순복음교회", "Hanoi Full Gospel Church"),
    AliasSpec("西鎮祠", "Tây Trấn Từ", language="vi", confidence=0.95),
    AliasSpec("풍흥 벽화마을", "Phung Hung Mural Village", confidence=0.95),
    AliasSpec("썸노래방", "Sseom Karaoke", confidence=0.85),
    AliasSpec("ロイヤルシティー", "Royal City", confidence=0.95),
    AliasSpec("버디플러스 하노이 지점", "Buddy Plus Hanoi Branch"),
    AliasSpec(
        "하노이 늘사랑교회 비전센터",
        "Hanoi Neulsarang Church Vision Center",
        confidence=0.85,
    ),
    AliasSpec("생명나무교회", "Tree of Life Church", confidence=0.85),
    AliasSpec("비타민노래방", "Vitamin Karaoke"),
    AliasSpec("하노이 강남스파", "Hanoi Gangnam Spa"),
    AliasSpec("드림골프존", "Dream Golf Zone"),
    AliasSpec("연스파", "Yeon Spa", confidence=0.85),
    AliasSpec("과일가게 골목", "Fruit Shop Alley", confidence=0.85),
    AliasSpec("河内羊肉", "Hanoi Lamb", confidence=0.8),
)

SKIPPED_NAMES = {
    "성당": "generic name",
    "公園": "generic name",
    "한국 교회": "generic name",
    "डॉल गेरू": "unclear transliteration",
    "神靈寺": "no reliable Hanoi-specific Latin name",
    "福恩寺": "no reliable Hanoi-specific Latin name",
    "*****": "quarantined invalid canonical name",
    ".": "quarantined invalid canonical name",
}


def load_source_urls(db: Session, entity_ids: list[str]) -> dict[str, str]:
    source_urls: dict[str, str] = {}
    for prop in db.scalars(
        select(KnowledgeProperty).where(
            KnowledgeProperty.entity_id.in_(entity_ids),
            KnowledgeProperty.key.in_(("source_link", "source_url", "google_maps_url")),
        )
    ):
        source_urls.setdefault(prop.entity_id, prop.value)
    return source_urls


def plan_aliases(
    db: Session,
) -> tuple[list[tuple[KnowledgeEntity, AliasSpec, str]], list[dict]]:
    specs = {spec.canonical_name: spec for spec in ALIAS_SPECS}
    entities = list(
        db.scalars(
            select(KnowledgeEntity).where(
                KnowledgeEntity.canonical_name.in_(tuple(specs))
            )
        )
    )
    source_urls = load_source_urls(db, [entity.id for entity in entities])
    existing = {
        (alias.entity_id, alias.alias.casefold())
        for alias in db.scalars(
            select(KnowledgeAlias).where(
                KnowledgeAlias.entity_id.in_([entity.id for entity in entities])
            )
        )
    }
    planned = []
    skipped = []
    found_names = set()
    for entity in entities:
        found_names.add(entity.canonical_name)
        spec = specs[entity.canonical_name]
        source_url = source_urls.get(entity.id)
        if not source_url:
            skipped.append({"name": entity.canonical_name, "reason": "missing source URL"})
        elif (entity.id, spec.alias.casefold()) in existing:
            skipped.append({"name": entity.canonical_name, "reason": "alias already exists"})
        else:
            planned.append((entity, spec, source_url))
    for missing_name in sorted(set(specs).difference(found_names)):
        skipped.append({"name": missing_name, "reason": "entity not found"})
    skipped.extend(
        {"name": name, "reason": reason}
        for name, reason in SKIPPED_NAMES.items()
    )
    return planned, skipped


def apply_aliases(
    db: Session,
    planned: list[tuple[KnowledgeEntity, AliasSpec, str]],
) -> None:
    for entity, spec, source_url in planned:
        db.add(
            KnowledgeAlias(
                entity_id=entity.id,
                alias=spec.alias,
                normalized_alias=normalize_knowledge_text(spec.alias),
                language=spec.language,
                alias_type="translated_name",
                source=source_url,
                provider=PROVIDER,
                status="imported",
                confidence=spec.confidence,
            )
        )
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        planned, skipped = plan_aliases(db)
        print(
            json.dumps(
                {
                    "candidateCount": len(planned),
                    "aliases": [
                        {
                            "entityId": entity.id,
                            "canonicalName": entity.canonical_name,
                            "alias": spec.alias,
                            "confidence": spec.confidence,
                            "source": source_url,
                        }
                        for entity, spec, source_url in planned
                    ],
                    "skipped": skipped,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if args.apply:
            apply_aliases(db, planned)
            print(f"Created {len(planned)} imported aliases.")


if __name__ == "__main__":
    main()
