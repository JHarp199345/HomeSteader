"""Local, editable Housing Services move-in workflow definition."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_RULES_PATH = PROJECT_ROOT / "config" / "move_in_packet.example.json"


def default_move_in_definition() -> dict:
    """Return the source-derived rules bundled with Homesteader."""
    return json.loads(EXAMPLE_RULES_PATH.read_text())


def load_move_in_definition(path: Path | None = None) -> dict:
    """Load a local move-in definition, falling back to the bundled example."""
    if path and path.exists():
        return json.loads(path.read_text())
    return default_move_in_definition()


def write_default_move_in_definition(path: Path) -> None:
    """Create an editable copy without replacing a user's existing policy."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(default_move_in_definition(), indent=2) + "\n")


def record_keys(definition: dict) -> set[str]:
    return {record["key"] for record in definition.get("records", [])}


def core_record_keys(definition: dict) -> set[str]:
    return {record["key"] for record in definition.get("records", []) if record.get("expected") == "core"}
