"""Local spreadsheet export for filtered correction findings."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORT_SCRIPT = PROJECT_ROOT / "tools" / "export_correction_report.mjs"


def export_correction_report(findings: list[dict], output_path: Path) -> Path:
    """Create one local XLSX report from already-derived audit findings.

    The exporter deliberately receives findings as values rather than a store:
    it cannot inspect, alter, or transmit the broader database.
    """
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required to create the local spreadsheet export.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False) as input_file:
        json.dump(findings, input_file)
        input_path = Path(input_file.name)
    try:
        completed = subprocess.run(
            [node, str(EXPORT_SCRIPT), str(input_path), str(output_path)],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"Could not create the local correction report. {detail}")
    finally:
        input_path.unlink(missing_ok=True)
    return output_path
