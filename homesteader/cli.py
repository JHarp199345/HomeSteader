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
    ingest_packet = subcommands.add_parser("ingest-packet", help="Ingest a coherent client packet without relying on file order")
    ingest_packet.add_argument("sources", type=Path, nargs="+")
    ingest_packet.add_argument("--label")
    start_packet = subcommands.add_parser("start-packet", help="Open a packet for documents scanned over time")
    start_packet.add_argument("--label")
    add_packet = subcommands.add_parser("add-to-packet", help="Add documents to an open packet")
    add_packet.add_argument("packet_id")
    add_packet.add_argument("sources", type=Path, nargs="+")
    close_packet = subcommands.add_parser("close-packet", help="Close an intake packet")
    close_packet.add_argument("packet_id")
    inbox = subcommands.add_parser("inbox", help="Inspect a local inbox without uploading files")
    inbox.add_argument("path", type=Path, nargs="?", default=Path("inbox"))
    review = subcommands.add_parser("review", help="List or resolve local review items")
    review_subcommands = review.add_subparsers(dest="review_command", required=True)
    review_subcommands.add_parser("list", help="List pending review items")
    resolve = review_subcommands.add_parser("resolve", help="Record a human review decision")
    resolve.add_argument("review_id")
    resolve.add_argument("--action", required=True, choices=["assign_existing", "create_person", "catalog_form", "accept_revision", "leave_unassigned"])
    resolve.add_argument("--entity-id")
    resolve.add_argument("--new-person-name")
    resolve.add_argument("--note")
    subcommands.add_parser("correction-findings", help="Print local correction-report rows as JSON")
    subcommands.add_parser("housing-schedule", help="Print derived Housing Services schedule status as JSON")
    import_proposal = subcommands.add_parser("import-ai-proposal", help="Validate and queue a local AI proposal JSON file")
    import_proposal.add_argument("proposal", type=Path)
    subcommands.add_parser("status", help="Show stored counts")
    args = parser.parse_args()
    store = HomesteaderStore(args.state)
    if args.command == "ingest":
        print(json.dumps(store.ingest(args.source), indent=2))
        store.save()
    elif args.command == "ingest-packet":
        print(json.dumps(store.ingest_packet(args.sources, label=args.label), indent=2))
        store.save()
    elif args.command == "start-packet":
        print(json.dumps(store.start_intake_packet(args.label), indent=2))
        store.save()
    elif args.command == "add-to-packet":
        print(json.dumps(store.add_to_intake_packet(args.packet_id, args.sources), indent=2))
        store.save()
    elif args.command == "close-packet":
        print(json.dumps(store.close_intake_packet(args.packet_id), indent=2))
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
    elif args.command == "correction-findings":
        print(json.dumps(store.correction_findings(), indent=2))
    elif args.command == "housing-schedule":
        print(json.dumps(store.housing_schedule_status(), indent=2))
    elif args.command == "import-ai-proposal":
        print(json.dumps(store.submit_ai_proposal(json.loads(args.proposal.read_text())), indent=2))
    else:
        print(json.dumps({key: len(value) for key, value in store.data.items()}, indent=2))


if __name__ == "__main__":
    main()
