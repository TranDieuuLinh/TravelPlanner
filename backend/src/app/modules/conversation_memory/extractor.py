"""Rule-based fact extractor implementation for Conversation Memory module."""

import re
import unicodedata
from typing import Sequence

from app.modules.conversation_memory.contract import (
    FactProvenance,
    MemoryFact,
    WorkingMemoryState,
    normalize_fact_value,
)


def remove_accents(input_str: str) -> str:
    """Remove Vietnamese accents and convert to lowercase."""
    nfkd_form = unicodedata.normalize("NFKD", input_str)
    only_ascii = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    return only_ascii.lower().replace("đ", "d")


DESTINATION_MAP = {
    "ha noi": "Hà Nội",
    "hn": "Hà Nội",
    "da nang": "Đà Nẵng",
    "dn": "Đà Nẵng",
    "ho chi minh": "TP. Hồ Chí Minh",
    "tp ho chi minh": "TP. Hồ Chí Minh",
    "tphcm": "TP. Hồ Chí Minh",
    "sai gon": "TP. Hồ Chí Minh",
    "sg": "TP. Hồ Chí Minh",
    "hcm": "TP. Hồ Chí Minh",
    "hoi an": "Hội An",
    "hue": "Huế",
    "da lat": "Đà Lạt",
    "phu quoc": "Phú Quốc",
    "sapa": "Sapa",
    "sa pa": "Sapa",
    "nha trang": "Nha Trang",
    "can tho": "Cần Thơ",
    "quang ninh": "Quảng Ninh",
    "ha long": "Quảng Ninh",
}

KNOWN_PLACES = [
    ("van mieu", "Văn Miếu"),
    ("ho hoan kiem", "Hồ Hoàn Kiếm"),
    ("ho gum", "Hồ Gươm"),
    ("ba na hills", "Bà Nà Hills"),
    ("chua cau", "Chùa Cầu"),
    ("cho ben thanh", "Chợ Bến Thành"),
    ("trang an", "Tràng An"),
    ("vinh ha long", "Vịnh Hạ Long"),
    ("pho co", "Phố Cổ"),
    ("dinh fansipan", "Đỉnh Fansipan"),
]

NUMBER_WORDS = {
    "mot": 1,
    "hai": 2,
    "ba": 3,
    "bon": 4,
    "nam": 5,
    "sau": 6,
    "bay": 7,
    "tam": 8,
    "chin": 9,
    "muoi": 10,
}


class RuleBasedFactExtractor:
    """Deterministic, rule-based fact extractor for Vietnamese conversation inputs."""

    async def extract_facts(
        self,
        message: str,
        current_memory: WorkingMemoryState,
        recent_messages: Sequence[dict] | None = None,
        turn: int = 1,
        message_id: str | None = None,
    ) -> Sequence[MemoryFact]:
        facts: list[MemoryFact] = []
        clean_msg = message.strip()
        no_accent_msg = remove_accents(clean_msg)
        excerpt = clean_msg[:200]

        # Transcript text may contain quoted prompt-injection instructions. It
        # is not a travel preference or a user confirmation, so do not project
        # facts from instruction-like content.
        if any(
            marker in no_accent_msg
            for marker in (
                "ignore previous instructions",
                "ignore all previous",
                "system prompt",
                "jailbreak",
                "bo qua huong dan truoc",
            )
        ):
            return []

        # 0. URL Extraction
        url_match = re.search(r"https?://[^\s]+", clean_msg)
        source_url_val = url_match.group(0) if url_match else None
        if source_url_val:
            facts.append(
                MemoryFact(
                    fact_id=f"f_url_{turn}_{len(facts)}",
                    fact_type="note",
                    key="note",
                    value=source_url_val,
                    value_type="string",
                    scope="chat",
                    status="active",
                    confirmed_by_user=False,
                    provenance=FactProvenance(
                        source_turn=turn,
                        source_message_id=message_id,
                        source_excerpt=excerpt,
                        extracted_by="rule_based_v1",
                        confidence=0.9,
                        source_url=source_url_val[:500],
                    ),
                )
            )

        # 1. Destination Extraction
        is_hypothetical = any(
            kw in no_accent_msg
            for kw in ["co the di", "neu di", "thu di", "gia su", "hoi ve", "tham khao"]
        )
        is_explicit_change = any(
            kw in no_accent_msg
            for kw in ["doi sang", "chuyen sang", "doi thanh", "muon doi", "xac nhan di", "chac chan di"]
        )
        is_direct_confirmation = any(
            kw in no_accent_msg
            for kw in ["xac nhan", "chac chan", "dong y", "toi chon"]
        )

        matched_dest = None
        for key, canonical in DESTINATION_MAP.items():
            pattern = r"\b" + re.escape(key) + r"\b"
            if re.search(pattern, no_accent_msg):
                matched_dest = canonical
                break

        if matched_dest:
            conf = 0.95 if (is_explicit_change or is_direct_confirmation) else (0.6 if is_hypothetical else 0.85)
            status = "active"
            facts.append(
                MemoryFact(
                    fact_id=f"f_dest_{turn}_{len(facts)}",
                    fact_type="destination",
                    key="destination",
                    value=matched_dest,
                    value_type="string",
                    scope="chat",
                    status=status,
                    confirmed_by_user=is_direct_confirmation or is_explicit_change,
                    provenance=FactProvenance(
                        source_turn=turn,
                        source_message_id=message_id,
                        source_excerpt=excerpt,
                        extracted_by="rule_based_v1",
                        confidence=conf,
                        source_url=source_url_val[:500] if source_url_val else None,
                    ),
                )
            )

        # 2. Duration Extraction
        dur_match = re.search(r"(\d+)\s*(ngay|d|dem|day|days)", no_accent_msg)
        dur_val = None
        if dur_match:
            dur_val = int(dur_match.group(1))
        else:
            for word, val in NUMBER_WORDS.items():
                if f"{word} ngay" in no_accent_msg:
                    dur_val = val
                    break
            if "mot tuan" in no_accent_msg or "1 tuan" in no_accent_msg:
                dur_val = 7

        if dur_val and 1 <= dur_val <= 90:
            facts.append(
                MemoryFact(
                    fact_id=f"f_dur_{turn}_{len(facts)}",
                    fact_type="duration",
                    key="duration",
                    value=dur_val,
                    value_type="number",
                    scope="chat",
                    status="active",
                    confirmed_by_user=is_direct_confirmation,
                    provenance=FactProvenance(
                        source_turn=turn,
                        source_message_id=message_id,
                        source_excerpt=excerpt,
                        extracted_by="rule_based_v1",
                        confidence=0.9,
                        source_url=source_url_val[:500] if source_url_val else None,
                    ),
                )
            )

        # 3. Travelers Extraction
        trv_match = re.search(r"(\d+)\s*(nguoi|pax|khach|thanh vien|ban)", no_accent_msg)
        trv_val = None
        if trv_match:
            trv_val = int(trv_match.group(1))
        elif "hai vo chong" in no_accent_msg or "2 vo chong" in no_accent_msg:
            trv_val = 2
        elif "mot minh" in no_accent_msg or "1 minh" in no_accent_msg:
            trv_val = 1

        if trv_val and 1 <= trv_val <= 50:
            facts.append(
                MemoryFact(
                    fact_id=f"f_trv_{turn}_{len(facts)}",
                    fact_type="travelers",
                    key="travelers",
                    value=trv_val,
                    value_type="number",
                    scope="chat",
                    status="active",
                    confirmed_by_user=is_direct_confirmation,
                    provenance=FactProvenance(
                        source_turn=turn,
                        source_message_id=message_id,
                        source_excerpt=excerpt,
                        extracted_by="rule_based_v1",
                        confidence=0.9,
                        source_url=source_url_val[:500] if source_url_val else None,
                    ),
                )
            )

        # 4. Budget Tier Extraction
        if any(kw in no_accent_msg for kw in ["tiet kiem", "gia re", "binh dan", "tai chinh hep"]):
            budget_tier = "low"
        elif any(kw in no_accent_msg for kw in ["sang trong", "cao cap", "resort", "vong tay sang"]):
            budget_tier = "high"
        elif any(kw in no_accent_msg for kw in ["trung binh", "vua phai", "hop ly"]):
            budget_tier = "medium"
        else:
            budget_tier = None

        if budget_tier:
            facts.append(
                MemoryFact(
                    fact_id=f"f_bud_{turn}_{len(facts)}",
                    fact_type="budget_tier",
                    key="budget_tier",
                    value=budget_tier,
                    value_type="string",
                    scope="chat",
                    status="active",
                    confirmed_by_user=is_direct_confirmation,
                    provenance=FactProvenance(
                        source_turn=turn,
                        source_message_id=message_id,
                        source_excerpt=excerpt,
                        extracted_by="rule_based_v1",
                        confidence=0.85,
                        source_url=source_url_val[:500] if source_url_val else None,
                    ),
                )
            )

        # 5. Place Candidate Extraction
        for norm_p, canonical_p in KNOWN_PLACES:
            if norm_p in no_accent_msg:
                facts.append(
                    MemoryFact(
                        fact_id=f"f_place_{turn}_{len(facts)}",
                        fact_type="place_candidate",
                        key="place_candidate",
                        value=canonical_p,
                        normalized_value=normalize_fact_value(canonical_p),
                        value_type="string",
                        scope="chat",
                        status="active",
                        confirmed_by_user=False,
                        provenance=FactProvenance(
                            source_turn=turn,
                            source_message_id=message_id,
                            source_excerpt=excerpt,
                            extracted_by="rule_based_v1",
                            confidence=0.85,
                            source_url=source_url_val[:500] if source_url_val else None,
                        ),
                    )
                )

        return facts
