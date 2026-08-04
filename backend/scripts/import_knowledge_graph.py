#!/usr/bin/env python3
"""Import legacy Knowledge Graph CSV data into PostgreSQL.

Usage:
    # Dry run (no changes)
    python -m scripts.import_knowledge_graph --dry-run

    # Replace mode (clear existing data first)
    python -m scripts.import_knowledge_graph --replace

    # Normal (idempotent - skip existing)
    python -m scripts.import_knowledge_graph

    # Custom directory
    python -m scripts.import_knowledge_graph --graph-dir /path/to/knowledge-graph-real-v2

    # Custom batch size
    python -m scripts.import_knowledge_graph --batch-size 500
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.modules.knowledge_graph.model import (
    KnowledgeAlias,
    KnowledgeEntity,
    KnowledgeProperty,
    KnowledgeRelationship,
)

# Batch size for CSV processing
DEFAULT_BATCH_SIZE = 1000

# Entity type prefix mapping
ENTITY_TYPE_PREFIX = {
    "Place": "place",
    "TravelPlace": "place",
    "Restaurant": "restaurant",
    "DrinkDessert": "drink",
    "Accommodation": "hotel",
    "Area": "area",
    "City": "city",
    "District": "district",
    "Activity": "activity",
    "Festival": "festival",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import legacy Knowledge Graph CSV data into PostgreSQL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - see what would be imported without making changes
  python -m scripts.import_knowledge_graph --dry-run

  # Normal import - idempotent, skips existing entities
  python -m scripts.import_knowledge_graph

  # Replace mode - clears existing KG data before import
  python -m scripts.import_knowledge_graph --replace

  # Custom graph directory
  python -m scripts.import_knowledge_graph --graph-dir /data/knowledge-graph-real-v2

  # Custom batch size
  python -m scripts.import_knowledge_graph --batch-size 500
        """,
    )
    parser.add_argument(
        "--graph-dir",
        type=Path,
        default=BACKEND_ROOT.parent / "knowledge-graph-real-v2",
        help="Path to knowledge-graph-real-v2 directory (default: ../knowledge-graph-real-v2)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Number of rows per batch (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Clear existing KG data before import (WARNING: destructive)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without making changes",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    return parser.parse_args()


def normalized(value: str) -> str:
    """Normalize text for matching."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks).split())


def entity_type_prefix(entity_type: str) -> str:
    """Get prefix for entity type."""
    return ENTITY_TYPE_PREFIX.get(entity_type, entity_type.lower()[:8])


def next_entity_id(entity_type: str, existing_ids: set[str]) -> str:
    """Generate next entity ID for a type."""
    prefix = entity_type_prefix(entity_type)
    counter = 1
    while f"{prefix}_{counter:06d}" in existing_ids:
        counter += 1
    return f"{prefix}_{counter:06d}"


def _read_csv_chunked(
    path: Path,
    batch_size: int,
    on_batch: callable,
    quiet: bool = False,
) -> int:
    """Read CSV file in chunks and process each batch.

    Args:
        path: Path to CSV file
        batch_size: Number of rows per batch
        on_batch: Callback function(batch: list[dict]) -> None
        quiet: Suppress progress output

    Returns:
        Total number of rows processed
    """
    if not path.exists():
        if not quiet:
            print(f"  [SKIP] File not found: {path}")
        return 0

    total = 0
    batch = []

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            batch.append(dict(row))
            if len(batch) >= batch_size:
                on_batch(batch)
                total += len(batch)
                if not quiet:
                    print(f"    Processed {total:,} rows...")
                batch = []

        if batch:
            on_batch(batch)
            total += len(batch)
            if not quiet:
                print(f"    Processed {total:,} rows...")

    return total


def import_entities(
    db: Session,
    graph_dir: Path,
    batch_size: int,
    dry_run: bool,
    quiet: bool,
) -> dict:
    """Import entities from entities.csv."""
    entities_path = graph_dir / "entities.csv"
    if not entities_path.exists():
        return {"imported": 0, "skipped": 0, "errors": 0}

    if not quiet:
        print("  Importing entities...")

    imported = 0
    skipped = 0
    errors = 0
    existing_ids: set[str] = set()

    # Get existing entity IDs
    from sqlalchemy import select
    existing = db.scalars(select(KnowledgeEntity.id)).all()
    existing_ids = set(existing)

    def process_batch(rows: list[dict]) -> None:
        nonlocal imported, skipped, errors
        for row in rows:
            entity_id = row.get("id", "").strip()
            if not entity_id:
                errors += 1
                continue

            name = row.get("name", "").strip()
            entity_type = row.get("type", "").strip()
            status = row.get("status", "draft").strip()

            if entity_id in existing_ids and not dry_run:
                skipped += 1
                continue

            try:
                entity = KnowledgeEntity(
                    id=entity_id,
                    canonical_name=name,
                    normalized_name=normalized(name),
                    entity_type=entity_type,
                    status=status,
                )
                if not dry_run:
                    db.add(entity)
                imported += 1
                existing_ids.add(entity_id)
            except Exception as exc:
                errors += 1
                if not quiet:
                    print(f"    Error importing entity {entity_id}: {exc}")

    _read_csv_chunked(entities_path, batch_size, process_batch, quiet)

    return {"imported": imported, "skipped": skipped, "errors": errors}


def import_aliases(
    db: Session,
    graph_dir: Path,
    batch_size: int,
    dry_run: bool,
    quiet: bool,
) -> dict:
    """Import aliases from aliases.csv."""
    aliases_path = graph_dir / "aliases.csv"
    if not aliases_path.exists():
        return {"imported": 0, "skipped": 0, "errors": 0}

    if not quiet:
        print("  Importing aliases...")

    imported = 0
    skipped = 0
    errors = 0
    existing_aliases: set[tuple[str, str]] = set()

    from sqlalchemy import select
    existing = db.scalars(
        select(KnowledgeAlias.entity_id, KnowledgeAlias.alias).select_from(KnowledgeAlias)
    ).all()
    existing_aliases = set(existing)

    def process_batch(rows: list[dict]) -> None:
        nonlocal imported, skipped, errors
        for row in rows:
            entity_id = row.get("entity_id", "").strip()
            alias = row.get("alias", "").strip()
            language = row.get("language", "en").strip()

            if not entity_id or not alias:
                errors += 1
                continue

            if (entity_id, alias) in existing_aliases and not dry_run:
                skipped += 1
                continue

            try:
                alias_record = KnowledgeAlias(
                    entity_id=entity_id,
                    alias=alias,
                    normalized_alias=normalized(alias),
                    language=language or "en",
                )
                if not dry_run:
                    db.add(alias_record)
                imported += 1
                existing_aliases.add((entity_id, alias))
            except Exception as exc:
                errors += 1
                if not quiet:
                    print(f"    Error importing alias {entity_id}/{alias}: {exc}")

    _read_csv_chunked(aliases_path, batch_size, process_batch, quiet)

    return {"imported": imported, "skipped": skipped, "errors": errors}


def import_properties(
    db: Session,
    graph_dir: Path,
    batch_size: int,
    dry_run: bool,
    quiet: bool,
) -> dict:
    """Import properties from properties.csv."""
    properties_path = graph_dir / "properties.csv"
    if not properties_path.exists():
        return {"imported": 0, "skipped": 0, "errors": 0}

    if not quiet:
        print("  Importing properties...")

    imported = 0
    skipped = 0
    errors = 0
    existing_props: set[tuple[str, str]] = set()

    from sqlalchemy import select
    existing = db.scalars(
        select(KnowledgeProperty.entity_id, KnowledgeProperty.key).select_from(KnowledgeProperty)
    ).all()
    existing_props = set(existing)

    def process_batch(rows: list[dict]) -> None:
        nonlocal imported, skipped, errors
        for row in rows:
            entity_id = row.get("entity_id", "").strip()
            key = row.get("key", "").strip()
            value = row.get("value", "").strip()
            source = row.get("source", "").strip()

            if not entity_id or not key:
                errors += 1
                continue

            if (entity_id, key) in existing_props and not dry_run:
                skipped += 1
                continue

            try:
                prop = KnowledgeProperty(
                    entity_id=entity_id,
                    key=key,
                    value=value,
                    source=source or None,
                )
                if not dry_run:
                    db.add(prop)
                imported += 1
                existing_props.add((entity_id, key))
            except Exception as exc:
                errors += 1
                if not quiet:
                    print(f"    Error importing property {entity_id}/{key}: {exc}")

    _read_csv_chunked(properties_path, batch_size, process_batch, quiet)

    return {"imported": imported, "skipped": skipped, "errors": errors}


def import_relationships(
    db: Session,
    graph_dir: Path,
    batch_size: int,
    dry_run: bool,
    quiet: bool,
) -> dict:
    """Import relationships from relationships.csv."""
    relationships_path = graph_dir / "relationships.csv"
    if not relationships_path.exists():
        return {"imported": 0, "skipped": 0, "errors": 0}

    if not quiet:
        print("  Importing relationships...")

    imported = 0
    skipped = 0
    errors = 0
    existing_rels: set[tuple[str, str, str]] = set()

    from sqlalchemy import select
    existing = db.scalars(
        select(
            KnowledgeRelationship.from_entity_id,
            KnowledgeRelationship.relationship,
            KnowledgeRelationship.to_entity_id,
        ).select_from(KnowledgeRelationship)
    ).all()
    existing_rels = set(existing)

    def process_batch(rows: list[dict]) -> None:
        nonlocal imported, skipped, errors
        for row in rows:
            from_id = row.get("from_entity_id", "").strip()
            relationship = row.get("relationship", "").strip()
            to_id = row.get("to_entity_id", "").strip()
            source = row.get("source", "").strip()
            recommendations_raw = row.get("recommendations", "").strip()

            if not from_id or not relationship or not to_id:
                errors += 1
                continue

            if (from_id, relationship, to_id) in existing_rels and not dry_run:
                skipped += 1
                continue

            try:
                recommendations = None
                if recommendations_raw:
                    try:
                        recommendations = json.loads(recommendations_raw)
                    except json.JSONDecodeError:
                        pass

                rel = KnowledgeRelationship(
                    from_entity_id=from_id,
                    relationship=relationship,
                    to_entity_id=to_id,
                    source=source or None,
                    recommendations=recommendations,
                )
                if not dry_run:
                    db.add(rel)
                imported += 1
                existing_rels.add((from_id, relationship, to_id))
            except Exception as exc:
                errors += 1
                if not quiet:
                    print(f"    Error importing relationship {from_id}/{relationship}/{to_id}: {exc}")

    _read_csv_chunked(relationships_path, batch_size, process_batch, quiet)

    return {"imported": imported, "skipped": skipped, "errors": errors}


def clear_knowledge_graph(db: Session) -> None:
    """Clear all knowledge graph data from the database."""
    from sqlalchemy import delete

    db.execute(delete(KnowledgeRelationship))
    db.execute(delete(KnowledgeProperty))
    db.execute(delete(KnowledgeAlias))
    db.execute(delete(KnowledgeEntity))
    db.commit()


def main() -> None:
    args = parse_args()

    graph_dir = args.graph_dir.resolve()
    if not graph_dir.exists():
        print(f"Error: Graph directory not found: {graph_dir}")
        sys.exit(1)

    if not (graph_dir / "entities.csv").exists():
        print(f"Error: entities.csv not found in {graph_dir}")
        sys.exit(1)

    print(f"Graph directory: {graph_dir}")
    print(f"Batch size: {args.batch_size}")

    if args.dry_run:
        print("\n[DRY RUN MODE - No changes will be made]\n")
    elif args.replace:
        print("\n[REPLACE MODE - Existing data will be cleared]\n")
    else:
        print("\n[IDEMPOTENT MODE - Existing data will be preserved]\n")

    # Create database connection
    engine = create_engine(settings.database_url, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        if args.replace and not args.dry_run:
            if not args.quiet:
                print("Clearing existing knowledge graph data...")
            clear_knowledge_graph(db)
            if not args.quiet:
                print("  Cleared.\n")

        # Import entities
        print("Importing entities...")
        entity_stats = import_entities(db, graph_dir, args.batch_size, args.dry_run, args.quiet)
        print(f"  Imported: {entity_stats['imported']}, Skipped: {entity_stats['skipped']}, Errors: {entity_stats['errors']}")

        if not args.dry_run:
            db.commit()
            if not args.quiet:
                print("  Committed.\n")

        # Import aliases
        print("Importing aliases...")
        alias_stats = import_aliases(db, graph_dir, args.batch_size, args.dry_run, args.quiet)
        print(f"  Imported: {alias_stats['imported']}, Skipped: {alias_stats['skipped']}, Errors: {alias_stats['errors']}")

        if not args.dry_run:
            db.commit()
            if not args.quiet:
                print("  Committed.\n")

        # Import properties
        print("Importing properties...")
        property_stats = import_properties(db, graph_dir, args.batch_size, args.dry_run, args.quiet)
        print(f"  Imported: {property_stats['imported']}, Skipped: {property_stats['skipped']}, Errors: {property_stats['errors']}")

        if not args.dry_run:
            db.commit()
            if not args.quiet:
                print("  Committed.\n")

        # Import relationships
        print("Importing relationships...")
        rel_stats = import_relationships(db, graph_dir, args.batch_size, args.dry_run, args.quiet)
        print(f"  Imported: {rel_stats['imported']}, Skipped: {rel_stats['skipped']}, Errors: {rel_stats['errors']}")

        if not args.dry_run:
            db.commit()
            if not args.quiet:
                print("  Committed.\n")

        # Summary
        total_imported = (
            entity_stats["imported"]
            + alias_stats["imported"]
            + property_stats["imported"]
            + rel_stats["imported"]
        )
        total_skipped = (
            entity_stats["skipped"]
            + alias_stats["skipped"]
            + property_stats["skipped"]
            + rel_stats["skipped"]
        )
        total_errors = (
            entity_stats["errors"]
            + alias_stats["errors"]
            + property_stats["errors"]
            + rel_stats["errors"]
        )

        print("\n" + "=" * 50)
        print("Import Summary")
        print("=" * 50)
        print(f"Entities:      {entity_stats['imported']:,} imported, {entity_stats['skipped']:,} skipped, {entity_stats['errors']:,} errors")
        print(f"Aliases:       {alias_stats['imported']:,} imported, {alias_stats['skipped']:,} skipped, {alias_stats['errors']:,} errors")
        print(f"Properties:    {property_stats['imported']:,} imported, {property_stats['skipped']:,} skipped, {property_stats['errors']:,} errors")
        print(f"Relationships: {rel_stats['imported']:,} imported, {rel_stats['skipped']:,} skipped, {rel_stats['errors']:,} errors")
        print("-" * 50)
        print(f"TOTAL:         {total_imported:,} imported, {total_skipped:,} skipped, {total_errors:,} errors")
        print("=" * 50)

        if args.dry_run:
            print("\n[DRY RUN COMPLETE - No changes were made]")
        elif total_errors > 0:
            print(f"\nWarning: {total_errors} errors occurred during import.")
            sys.exit(1)
        else:
            print("\nImport completed successfully!")

    finally:
        db.close()


if __name__ == "__main__":
    main()
