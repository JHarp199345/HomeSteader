"""Local inbox inspection; this module never transmits a file."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True)
class InboxItem:
    path: Path
    sha256: str
    size_bytes: int


def inspect_inbox(path: Path) -> list[InboxItem]:
    """List local files and hashes without moving, reading externally, or uploading them."""
    if not path.exists():
        return []
    return [
        InboxItem(item, sha256(item.read_bytes()).hexdigest(), item.stat().st_size)
        for item in sorted(path.iterdir())
        if item.is_file() and not item.name.startswith(".")
    ]
