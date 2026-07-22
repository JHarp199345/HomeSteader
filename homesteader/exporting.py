"""Local, selected export of already-preserved source evidence."""

from __future__ import annotations

from pathlib import Path
import re

from pypdf import PdfReader, PdfWriter


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._ -]+", "_", value).strip(" .") or "document"


def export_logical_parts(document: dict, part_ids: list[str], destination: Path) -> list[Path]:
    """Write selected logical PDF parts in their defined packet order.

    The function only reads the archived original. It does not mutate the
    archive, source metadata, or page order in the source PDF.
    """
    structure = document.get("logical_document_structure")
    if not structure:
        raise ValueError("This source has no recognized logical-document structure.")
    selected = [part for part in structure["parts"] if part["id"] in set(part_ids)]
    if not selected:
        raise ValueError("Select at least one logical document to export.")
    source = Path(document["stored_source_path"])
    if source.suffix.casefold() != ".pdf":
        raise ValueError("Logical page export is currently available for PDF sources only.")
    reader = PdfReader(source)
    outputs: list[Path] = []
    for part in sorted(selected, key=lambda item: item["order"]):
        folder = destination / f"{part['order']:02d}_{safe_name(part['section'])}"
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / f"{part['order']:02d}_{safe_name(part['title'])}.pdf"
        writer = PdfWriter()
        for page_number in range(part["start_page"], part["end_page"] + 1):
            writer.add_page(reader.pages[page_number - 1])
        with output.open("wb") as handle:
            writer.write(handle)
        outputs.append(output)
    return outputs
