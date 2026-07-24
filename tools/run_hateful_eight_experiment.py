"""Run a local-only, fictional Hateful Eight intake experiment.

This is a diagnostic harness, not the automated test suite.  It requires a
separately generated fictional fixture directory and never points at HMIS,
CHAMP, Google Drive, or live participant records.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from homesteader.core import HomesteaderStore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES = ROOT / "Homesteader Test Documents" / "HATEFUL_EIGHT_FICTIONAL_TRAINING_V3_MAPPED"


def pdf_sources(folder: Path) -> list[Path]:
    sources = sorted(folder.glob("*.pdf"))
    if not sources:
        raise FileNotFoundError(f"No fictional PDF fixtures found in {folder}.")
    return sources


def run_phase_1(fixtures: Path, state_dir: Path) -> None:
    print("\n" + "=" * 66)
    print(" PHASE 1: MASS UPLOAD & RELATIONSHIP GRAPH RECONCILIATION")
    print("=" * 66)
    store = HomesteaderStore(state_dir / "phase1.json")
    sources = pdf_sources(fixtures / "01_FULL_MIXED_UPLOAD")
    print(f"Ingesting {len(sources)} mixed fictional source PDFs...")
    for source in sources:
        store.ingest(source)

    print("\nPhase 1 ingestion summary:")
    print(f"  Documents: {len(store.data.get('documents', []))}")
    print(f"  Entities: {len(store.data.get('entities', []))}")
    print(f"  Relationships: {len(store.data.get('relationships', []))}")
    people = [entity for entity in store.data.get("entities", []) if entity.get("kind") == "person"]
    print(f"\nParticipant file checks ({len(people)} participants):")
    for person in people:
        summary = store.participant_file(person["id"])
        identifier = summary["attributes"].get("hmis_id") or summary["attributes"].get("temporary_id") or "No ID"
        print(f"  {summary['name']} [{identifier}] -> {len(summary['documents'])} linked document(s), {len(summary['related_entities'])} connection(s)")


def run_phase_2_and_3(fixtures: Path, state_dir: Path) -> None:
    print("\n" + "=" * 66)
    print(" PHASE 2: PARTIAL / OUT-OF-ORDER UPLOAD & CORRECTION AUDIT")
    print("=" * 66)
    store = HomesteaderStore(state_dir / "phase2.json")
    sources = pdf_sources(fixtures / "02_PARTIAL_OUT_OF_ORDER_UPLOAD")
    print(f"Ingesting {len(sources)} partial fictional documents...")
    for source in sources:
        store.ingest(source)

    findings = store.correction_findings()
    print(f"\nCorrection findings: {len(findings)}")
    for finding in findings[:6]:
        print(f"  [{finding['category']}] {finding['document'] or 'Participant record'}")
        print(f"    Recommended: {finding['recommendation']}")

    print("\n" + "=" * 66)
    print(" PHASE 3: FOLLOW-UP RECORDS & EXACT-DUPLICATE PROTECTION")
    print("=" * 66)
    follow_up = pdf_sources(fixtures / "03_CORRECTION_AND_MISSING_RECORD_FOLLOW_UP")
    duplicates = pdf_sources(fixtures / "04_EXACT_DUPLICATE_UPLOADS")
    for source in follow_up:
        store.ingest(source)
    print(f"Follow-up records ingested: {len(follow_up)}")
    print(f"Correction findings after follow-up: {len(store.correction_findings())}")

    duplicate_results = [store.ingest(source) for source in duplicates]
    review_count = sum(result.get("status") == "needs_review" for result in duplicate_results)
    print(f"Exact duplicate uploads submitted: {len(duplicates)}")
    print(f"Duplicate uploads routed to review: {review_count}")
    print(f"Superseding links created only after confirmation: {len([rel for rel in store.data.get('relationships', []) if rel.get('type') == 'supersedes_for_fields'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local fictional Hateful Eight experiment.")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES, help="Fictional training fixture root.")
    args = parser.parse_args()
    fixtures = args.fixtures.expanduser().resolve()
    if not fixtures.is_dir():
        raise SystemExit(f"Fictional fixture directory was not found: {fixtures}")
    with tempfile.TemporaryDirectory(prefix="homesteader-hateful-eight-") as temporary:
        state_dir = Path(temporary)
        run_phase_1(fixtures, state_dir)
        run_phase_2_and_3(fixtures, state_dir)


if __name__ == "__main__":
    main()
