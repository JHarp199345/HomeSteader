#!/usr/bin/env python3
"""Score a local vision proposal against a fictional fixture's known answer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a review-only vision proposal against a fictional expected-result file.")
    parser.add_argument("proposal", type=Path)
    parser.add_argument("expected", type=Path)
    args = parser.parse_args()
    proposal = json.loads(args.proposal.read_text())
    expected = json.loads(args.expected.read_text())
    proposed_facts = {fact["field"]: fact["value"] for fact in proposal.get("facts", [])}
    expected_facts = expected["facts"]
    correct = [field for field, value in expected_facts.items() if proposed_facts.get(field) == value]
    missing = [field for field in expected_facts if field not in proposed_facts]
    incorrect = [field for field, value in expected_facts.items() if field in proposed_facts and proposed_facts[field] != value]
    forbidden = [field for field in expected.get("must_not_propose", []) if field in proposed_facts]
    print(json.dumps({
        "provider_id": proposal.get("provider_id"),
        "document_type_expected": expected["document_type"],
        "document_type_returned": proposal.get("document_type"),
        "document_type_correct": proposal.get("document_type") == expected["document_type"],
        "required_fields": len(expected_facts),
        "correct_fields": correct,
        "missing_fields": missing,
        "incorrect_fields": incorrect,
        "forbidden_fields_proposed": forbidden,
        "field_accuracy": len(correct) / len(expected_facts) if expected_facts else 1.0,
        "model_reported_confidence": proposal.get("overall_confidence"),
    }, indent=2))


if __name__ == "__main__":
    main()
