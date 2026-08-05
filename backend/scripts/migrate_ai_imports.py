#!/usr/bin/env python3
"""Migrate AI Import legacy JSON data into PostgreSQL.

Usage:
    # Dry run (no changes)
    python -m scripts.migrate_ai_imports --dry-run

    # Normal (idempotent - skip existing)
    python -m scripts.migrate_ai_imports

    # Replace mode (reimport existing)
    python -m scripts.migrate_ai_imports --replace

    # Custom directory
    python -m scripts.migrate_ai_imports --import-dir /path/to/knowledge-graph-imports
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.modules.knowledge_graph.model import (
    KnowledgeGraphImport,
    KnowledgeGraphImportEdge,
    KnowledgeGraphImportNode,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate legacy AI Import JSON data into PostgreSQL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - see what would be imported without making changes
  python -m scripts.migrate_ai_imports --dry-run

  # Normal import - idempotent, skips existing imports
  python -m scripts.migrate_ai_imports

  # Replace mode - reimports existing imports
  python -m scripts.migrate_ai_imports --replace
        """,
    )
    parser.add_argument(
        "--import-dir",
        type=Path,
        default=BACKEND_ROOT / "var" / "knowledge-graph-imports",
        help="Path to knowledge-graph-imports directory (default: ../backend/var/knowledge-graph-imports)",
    )
    parser.add_argument(
        "--legacy-file",
        type=Path,
        default=BACKEND_ROOT / "var" / "knowledge-graph-imports.json",
        help="Path to legacy knowledge-graph-imports.json file",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Reimport existing imports (delete and recreate)",
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


def _parse_datetime(value) -> datetime | None:
    """Parse datetime from string or return None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def migrate_imports(
    db: Session,
    import_dir: Path,
    legacy_file: Path,
    replace: bool,
    dry_run: bool,
    quiet: bool,
) -> dict:
    """Migrate AI Import data from JSON files."""
    imported = 0
    skipped = 0
    errors = 0
    all_job_files: list[Path] = []

    # Collect all JSON files
    if import_dir.exists() and import_dir.is_dir():
        all_job_files.extend(sorted(import_dir.glob("*.json")))

    legacy_jobs: list[dict] = []
    if legacy_file.exists():
        try:
            data = json.loads(legacy_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                legacy_jobs = data
            elif isinstance(data, dict):
                legacy_jobs = data.get("jobs", [])
        except (json.JSONDecodeError, OSError):
            if not quiet:
                print(f"  Warning: Could not read legacy file: {legacy_file}")

    if not quiet:
        print(f"Found {len(all_job_files)} job files in directory")
        print(f"Found {len(legacy_jobs)} jobs in legacy file")

    # Build set of existing import IDs
    from sqlalchemy import select, delete
    existing_ids = set()
    existing = db.scalars(select(KnowledgeGraphImport.id)).all()
    existing_ids = set(existing)

    # Process legacy file first
    for job_data in legacy_jobs:
        import_id = job_data.get("id", "")
        if not import_id:
            errors += 1
            continue

        if import_id in existing_ids and not replace:
            skipped += 1
            continue

        try:
            if replace and import_id in existing_ids and not dry_run:
                # Delete existing
                db.execute(
                    delete(KnowledgeGraphImportEdge).where(
                        KnowledgeGraphImportEdge.import_id == import_id
                    )
                )
                db.execute(
                    delete(KnowledgeGraphImportNode).where(
                        KnowledgeGraphImportNode.import_id == import_id
                    )
                )
                db.execute(
                    delete(KnowledgeGraphImport).where(
                        KnowledgeGraphImport.id == import_id
                    )
                )

            if not dry_run:
                _save_import_job(db, import_id, job_data)
            imported += 1
            existing_ids.add(import_id)
        except Exception as exc:
            errors += 1
            if not quiet:
                print(f"  Error importing {import_id}: {exc}")

    # Process directory files
    for job_file in all_job_files:
        import_id = job_file.stem
        if import_id in existing_ids and not replace:
            skipped += 1
            continue

        try:
            job_data = json.loads(job_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            errors += 1
            if not quiet:
                print(f"  Error reading {job_file}: {exc}")
            continue

        if not isinstance(job_data, dict):
            errors += 1
            continue

        if replace and import_id in existing_ids and not dry_run:
            db.execute(
                delete(KnowledgeGraphImportEdge).where(
                    KnowledgeGraphImportEdge.import_id == import_id
                )
            )
            db.execute(
                delete(KnowledgeGraphImportNode).where(
                    KnowledgeGraphImportNode.import_id == import_id
                )
            )
            db.execute(
                delete(KnowledgeGraphImport).where(
                    KnowledgeGraphImport.id == import_id
                )
            )

        try:
            if not dry_run:
                _save_import_job(db, import_id, job_data)
            imported += 1
            existing_ids.add(import_id)
        except Exception as exc:
            errors += 1
            if not quiet:
                print(f"  Error importing {import_id}: {exc}")

    if not dry_run:
        db.commit()

    return {"imported": imported, "skipped": skipped, "errors": errors}


def _save_import_job(db: Session, import_id: str, job_data: dict) -> None:
    """Save a single import job with its nodes and edges."""
    nodes = job_data.get("nodes", []) or []
    edges = job_data.get("edges", []) or []

    # Parse timestamps
    created_at = _parse_datetime(job_data.get("created_at")) or datetime.now(timezone.utc)
    applied_at = _parse_datetime(job_data.get("applied_at"))

    job = KnowledgeGraphImport(
        id=import_id,
        source_label=job_data.get("source_label", ""),
        source_url=job_data.get("source_url"),
        source_content=job_data.get("source_content", ""),
        status=job_data.get("status", "failed"),
        schema_version=job_data.get("schema_version", ""),
        ontology_version=job_data.get("ontology_version", ""),
        dataset_hash=job_data.get("dataset_hash", ""),
        warnings=job_data.get("warnings") or [],
        node_count=len(nodes),
        edge_count=len(edges),
        issue_count=job_data.get("issue_count", 0),
        created_by=job_data.get("created_by", 0),
        created_at=created_at,
        applied_at=applied_at,
        applied_dataset_hash=job_data.get("applied_dataset_hash"),
        error_message=job_data.get("error_message"),
    )
    db.add(job)

    # Save nodes
    for node_data in nodes:
        node = KnowledgeGraphImportNode(
            import_id=import_id,
            temp_id=node_data.get("temp_id", ""),
            entity_id=node_data.get("entity_id", ""),
            type=node_data.get("type", ""),
            canonical_name=node_data.get("canonical_name", ""),
            aliases=node_data.get("aliases") or [],
            properties=node_data.get("properties") or {},
            evidence=node_data.get("evidence") or [],
            confidence=node_data.get("confidence", 0.5),
            match_status=node_data.get("match_status", "new"),
            match_candidates=node_data.get("match_candidates") or [],
            selected_entity_id=node_data.get("selected_entity_id"),
            decision=node_data.get("decision", "pending"),
            validation_issues=node_data.get("validation_issues") or [],
            required_properties=node_data.get("required_properties") or [],
            optional_properties=node_data.get("optional_properties") or [],
        )
        db.add(node)

    # Save edges
    for edge_data in edges:
        edge = KnowledgeGraphImportEdge(
            import_id=import_id,
            temp_id=edge_data.get("temp_id", ""),
            from_ref=edge_data.get("from_ref", ""),
            relationship=edge_data.get("relationship", ""),
            to_ref=edge_data.get("to_ref", ""),
            recommendations=edge_data.get("recommendations") or [],
            source=edge_data.get("source", ""),
            evidence=edge_data.get("evidence") or [],
            confidence=edge_data.get("confidence", 0.5),
            match_status=edge_data.get("match_status", "new"),
            decision=edge_data.get("decision", "pending"),
            validation_issues=edge_data.get("validation_issues") or [],
        )
        db.add(edge)

    db.flush()


def main() -> None:
    args = parse_args()

    import_dir = args.import_dir.resolve()
    legacy_file = args.legacy_file.resolve()

    if not import_dir.exists() and not legacy_file.exists():
        print("Error: No import data found.")
        print(f"  Directory: {import_dir}")
        print(f"  Legacy file: {legacy_file}")
        sys.exit(1)

    print(f"Import directory: {import_dir}")
    print(f"Legacy file: {legacy_file}")

    if args.dry_run:
        print("\n[DRY RUN MODE - No changes will be made]\n")
    elif args.replace:
        print("\n[REPLACE MODE - Existing imports will be reimported]\n")
    else:
        print("\n[IDEMPOTENT MODE - Existing imports will be preserved]\n")

    # Create database connection
    engine = create_engine(settings.database_url, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        stats = migrate_imports(
            db,
            import_dir,
            legacy_file,
            replace=args.replace,
            dry_run=args.dry_run,
            quiet=args.quiet,
        )

        print("\n" + "=" * 50)
        print("Migration Summary")
        print("=" * 50)
        print(f"Imported: {stats['imported']}")
        print(f"Skipped:  {stats['skipped']}")
        print(f"Errors:   {stats['errors']}")
        print("=" * 50)

        if args.dry_run:
            print("\n[DRY RUN COMPLETE - No changes were made]")
        elif stats["errors"] > 0:
            print(f"\nWarning: {stats['errors']} errors occurred during migration.")
            sys.exit(1)
        else:
            print("\nMigration completed successfully!")

    finally:
        db.close()


if __name__ == "__main__":
    main()
