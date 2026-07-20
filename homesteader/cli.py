from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import HomesteaderStore
from .inbox import inspect_inbox


def main() -> None:
    parser = argparse.ArgumentParser(description="Homesteader local proof-of-concept")
    parser.add_argument("--state", type=Path, default=Path("data/homesteader.json"))
    subcommands = parser.add_subparsers(dest="command", required=True)
    ingest = subcommands.add_parser("ingest", help="Ingest a fictional plain-text document")
    ingest.add_argument("source", type=Path)
    inbox = subcommands.add_parser("inbox", help="Inspect a local inbox without uploading files")
    inbox.add_argument("path", type=Path, nargs="?", default=Path("inbox"))
    review = subcommands.add_parser("review", help="List or resolve local review items")
    review_subcommands = review.add_subparsers(dest="review_command", required=True)
    review_subcommands.add_parser("list", help="List pending review items")
    resolve = review_subcommands.add_parser("resolve", help="Record a human review decision")
    resolve.add_argument("review_id")
    resolve.add_argument("--action", required=True, choices=["assign_existing", "create_person", "leave_unassigned"])
    resolve.add_argument("--entity-id")
    resolve.add_argument("--new-person-name")
    resolve.add_argument("--note")
    subcommands.add_parser("status", help="Show stored counts")
    args = parser.parse_args()
    store = HomesteaderStore(args.state)
    if args.command == "ingest":
        print(json.dumps(store.ingest(args.source), indent=2))
        store.save()
    elif args.command == "inbox":
        print(json.dumps([
            {"path": str(item.path), "sha256": item.sha256, "size_bytes": item.size_bytes}
            for item in inspect_inbox(args.path)
        ], indent=2))
    elif args.command == "review":
        if args.review_command == "list":
            print(json.dumps(store.pending_reviews(), indent=2))
        else:
            print(json.dumps(store.resolve_review(args.review_id, args.action, entity_id=args.entity_id, new_person_name=args.new_person_name, note=args.note), indent=2))
            store.save()
    else:
        print(json.dumps({key: len(value) for key, value in store.data.items()}, indent=2))


if __name__ == "__main__":
    main()
