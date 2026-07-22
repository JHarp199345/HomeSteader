"""Local, user-editable maps of logical documents inside composite PDFs."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_LAYOUTS_PATH = PROJECT_ROOT / "config" / "logical_document_layouts.example.json"


def default_layouts() -> list[dict]:
    return json.loads(EXAMPLE_LAYOUTS_PATH.read_text())["layouts"]


def load_logical_layouts(path: Path) -> list[dict]:
    """Read the local packet-definition file, falling back to the example."""
    if not path.exists():
        return default_layouts()
    data = json.loads(path.read_text())
    layouts = data.get("layouts", [])
    return layouts if isinstance(layouts, list) else default_layouts()


def write_default_logical_layouts(path: Path) -> Path:
    """Create a local editable copy once; never overwrite local adjustments."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(EXAMPLE_LAYOUTS_PATH.read_text())
    return path


def save_logical_layouts(path: Path, layouts: list[dict]) -> Path:
    """Persist validated user-maintained definitions on this local computer."""
    for layout in layouts:
        if not layout.get("layout_id") or not layout.get("title"):
            raise ValueError("Each packet definition needs an identifier and a title.")
        for part in layout.get("parts", []):
            start, end = int(part["start_page"]), int(part["end_page"])
            if start < 1 or end < start:
                raise ValueError(f"Invalid page range for '{part.get('title', 'unnamed logical document')}'.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"layouts": layouts}, indent=2) + "\n")
    return path


def logical_document_parts(text: str, page_count: int, layouts: list[dict] | None = None) -> dict | None:
    """Recognize a known composite packet and return a human-readable map.

    A definition matches only if its minimum page count and every configured
    marker occur. Similar PDFs remain ordinary sources for review.
    """
    upper = text.upper()
    for layout in layouts or default_layouts():
        if page_count < int(layout.get("minimum_pages", 1)):
            continue
        markers = [str(marker).upper() for marker in layout.get("recognition", {}).get("all_text_markers", [])]
        if not markers or not all(marker in upper for marker in markers):
            continue
        parts = layout.get("parts", [])
        if not parts:
            continue
        return {
            "layout_id": layout["layout_id"],
            "title": layout["title"],
            "page_count": page_count,
            "parts": [
                {
                    "id": part["id"],
                    "title": part["title"],
                    "start_page": int(part["start_page"]),
                    "end_page": int(part["end_page"]),
                    "section": part["section"],
                    "order": index,
                    "required_for": part.get("required_for", []),
                }
                for index, part in enumerate(parts, start=1)
            ],
        }
    return None
