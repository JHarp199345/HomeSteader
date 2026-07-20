"""Local-only workspace for packet intake and human review."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
from uuid import uuid4

from nicegui import ui

from homesteader.core import HomesteaderStore


LOCAL_HOST = "127.0.0.1"


def find_available_port(preferred_port: int, attempts: int = 100) -> int:
    for port in range(preferred_port, preferred_port + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
            candidate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                candidate.bind((LOCAL_HOST, port))
            except OSError:
                continue
            return port
    raise RuntimeError("No local workspace port is available.")


def build_workspace(store: HomesteaderStore, inbox_path: Path) -> None:
    ui.colors(primary="#0f766e", secondary="#475569", accent="#b45309", positive="#15803d", negative="#b91c1c")
    ui.add_head_html("""
        <style>
          body { background: #f7f8f6; color: #17221f; }
          .page-shell { max-width: 1280px; margin: 0 auto; padding: 24px; }
          .metric, .panel { background: #fff; border: 1px solid #d9dfd9; border-radius: 8px; padding: 16px; }
          .metric { min-width: 150px; }
          .muted { color: #60706a; }
        </style>
    """)

    with ui.header().classes("items-center justify-between bg-white text-slate-900 border-b border-slate-200"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("folder_shared", size="26px", color="primary")
            ui.label("Homesteader").classes("text-xl font-semibold")
            ui.label("Local workspace").classes("text-sm muted")
        ui.label("This computer only").classes("text-sm muted")

    with ui.column().classes("page-shell w-full gap-5"):
        with ui.row().classes("items-center justify-between w-full"):
            ui.label("Intake packets").classes("text-2xl font-semibold")
            refresh_button = ui.button(icon="refresh").props("flat round").tooltip("Refresh workspace")

        metrics = ui.row().classes("w-full gap-3 flex-wrap")
        packet_panel = ui.column().classes("panel w-full gap-3")
        review_panel = ui.column().classes("panel w-full gap-3")
        detached_panel = ui.column().classes("panel w-full gap-3")

        selected_packet_id: str | None = None

        def metrics_values() -> list[tuple[str, int]]:
            open_packets = store.open_intake_packets()
            pending = store.pending_reviews()
            return [
                ("Open packets", len(open_packets)),
                ("Needs review", len(pending)),
                ("Documents", len(store.data["documents"])),
                ("Clients", len([item for item in store.data["entities"] if item["kind"] == "person"])),
            ]

        def refresh_metrics() -> None:
            metrics.clear()
            with metrics:
                for label, value in metrics_values():
                    with ui.column().classes("metric gap-0"):
                        ui.label(str(value)).classes("text-2xl font-semibold")
                        ui.label(label).classes("text-sm muted")

        def selected_packet() -> dict | None:
            return next((packet for packet in store.open_intake_packets() if packet["id"] == selected_packet_id), None)

        def refresh_packets() -> None:
            nonlocal selected_packet_id
            packets = store.open_intake_packets()
            if selected_packet_id not in {packet["id"] for packet in packets}:
                selected_packet_id = packets[0]["id"] if packets else None
            packet_panel.clear()
            with packet_panel:
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Open packets").classes("text-lg font-semibold")
                    ui.button("New packet", icon="create_new_folder", on_click=open_new_packet_dialog).props("no-caps")
                if not packets:
                    ui.label("No packet is open.").classes("muted")
                    return
                options = {packet["id"]: f"{packet['label']} | {len(packet['document_ids'])} documents" for packet in packets}
                selector = ui.select(options, value=selected_packet_id, label="Active packet").classes("w-full")

                def change_packet() -> None:
                    nonlocal selected_packet_id
                    selected_packet_id = selector.value
                    refresh_detached()

                selector.on("update:model-value", change_packet)
                packet = selected_packet()
                if packet:
                    ui.label(f"{len(packet['document_ids'])} documents | {len(packet['intake_occurrence_ids'])} scans received").classes("text-sm muted")
                    if packet.get("proposed_person_id"):
                        person = next((item for item in store.data["entities"] if item["id"] == packet["proposed_person_id"]), None)
                        ui.label(f"Proposed client: {person['name'] if person else 'available'}").classes("text-sm")
                    if packet.get("anchor_conflict"):
                        ui.label(packet["anchor_conflict"]).classes("text-sm text-red-700")
                    upload = ui.upload(label="Add documents", multiple=True, auto_upload=True).props('accept=".pdf,.txt"')
                    upload.on_upload(receive_packet_upload)
                    with ui.row().classes("gap-2 flex-wrap"):
                        ui.button("Process new scans", icon="folder_open", on_click=process_new_scans).props("outline no-caps")
                        ui.button("Close packet", icon="task_alt", on_click=close_selected_packet).props("outline no-caps")

        def receive_packet_upload(event) -> None:
            packet = selected_packet()
            if not packet:
                ui.notify("Open a packet before adding documents.", type="warning")
                return
            inbox_path.mkdir(parents=True, exist_ok=True)
            destination = inbox_path / f"upload-{uuid4()}-{Path(event.name).name}"
            destination.write_bytes(event.content.read())
            try:
                store.add_to_intake_packet(packet["id"], [destination])
                store.save()
            except ValueError as error:
                ui.notify(str(error), type="negative")
                return
            ui.notify(f"Added {event.name} to the active packet.", type="positive")
            refresh_workspace()

        def close_selected_packet() -> None:
            packet = selected_packet()
            if not packet:
                return
            store.close_intake_packet(packet["id"])
            store.save()
            ui.notify("Packet closed.", type="positive")
            refresh_workspace()

        def process_new_scans() -> None:
            packet = selected_packet()
            if not packet:
                return
            result = store.ingest_inbox(inbox_path, packet_id=packet["id"])
            store.save()
            if result["processed"]:
                ui.notify(f"Added {len(result['processed'])} new scan{'s' if len(result['processed']) != 1 else ''}.", type="positive")
            else:
                ui.notify("No new scans found.")
            refresh_workspace()

        def open_new_packet_dialog() -> None:
            with ui.dialog() as dialog, ui.card().classes("w-96"):
                ui.label("New intake packet").classes("text-lg font-semibold")
                label = ui.input("Packet name").classes("w-full")
                with ui.row().classes("w-full justify-end"):
                    ui.button("Cancel", on_click=dialog.close).props("flat no-caps")

                    def create_packet() -> None:
                        nonlocal selected_packet_id
                        packet = store.start_intake_packet(label.value or None)
                        store.save()
                        selected_packet_id = packet["id"]
                        dialog.close()
                        refresh_workspace()

                    ui.button("Create", icon="create_new_folder", on_click=create_packet).props("no-caps")
            dialog.open()

        def refresh_detached() -> None:
            detached_panel.clear()
            with detached_panel:
                ui.label("Detached documents").classes("text-lg font-semibold")
                packet = selected_packet()
                documents = [document for document in store.data["documents"] if not document.get("intake_packet_id")]
                if not documents:
                    ui.label("No detached documents.").classes("muted")
                for document in documents[-10:]:
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label(document["original_name"]).classes("text-sm")
                        if packet:
                            ui.button(icon="add_link", on_click=lambda document=document: attach_document(document["id"])).props("flat round").tooltip("Add to active packet")

        def attach_document(document_id: str) -> None:
            packet = selected_packet()
            if not packet:
                return
            try:
                store.attach_document_to_intake_packet(packet["id"], document_id)
                store.save()
            except ValueError as error:
                ui.notify(str(error), type="negative")
                return
            refresh_workspace()

        def refresh_reviews() -> None:
            review_panel.clear()
            with review_panel:
                ui.label("Needs review").classes("text-lg font-semibold")
                reviews = store.pending_reviews()
                if not reviews:
                    ui.label("Nothing needs review.").classes("muted")
                for review in reviews[:12]:
                    document = next((item for item in store.data["documents"] if item["id"] == review["document_id"]), None)
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(document["original_name"] if document else "Document review").classes("font-medium text-sm")
                            ui.label(review["reason"]).classes("text-sm muted")
                        ui.button("Review", icon="fact_check", on_click=lambda review=review: open_review_dialog(review)).props("outline no-caps")

        def open_review_dialog(review: dict) -> None:
            document = next((item for item in store.data["documents"] if item["id"] == review["document_id"]), None)
            people = [entity for entity in store.data["entities"] if entity["kind"] == "person"]
            options = {person["id"]: person["name"] for person in people}
            proposed = review.get("proposed_person_id")
            proposed_name = document["extracted"].get("participant") if document else ""
            with ui.dialog() as dialog, ui.card().classes("w-[42rem] max-w-full"):
                ui.label("Review document").classes("text-lg font-semibold")
                ui.label(document["original_name"] if document else "Document").classes("text-sm muted")
                ui.label(review["reason"]).classes("text-sm")
                if document and document.get("source_text"):
                    ui.textarea("Source text", value=document["source_text"][:3000]).props("readonly").classes("w-full")
                existing = ui.select(options, value=proposed, label="File with client").classes("w-full")
                new_name = ui.input("Or create provisional client", value=proposed_name or "").classes("w-full")
                note = ui.textarea("Decision note").classes("w-full")

                def resolve(action: str) -> None:
                    try:
                        if action == "assign_existing":
                            store.resolve_review(review["id"], action, entity_id=existing.value, note=note.value or None)
                        elif action == "create_person":
                            store.resolve_review(review["id"], action, new_person_name=new_name.value or None, note=note.value or None)
                        else:
                            store.resolve_review(review["id"], action, note=note.value or None)
                        store.save()
                    except ValueError as error:
                        ui.notify(str(error), type="negative")
                        return
                    dialog.close()
                    ui.notify("Review recorded.", type="positive")
                    refresh_workspace()

                with ui.row().classes("w-full justify-between flex-wrap"):
                    ui.button("Leave unassigned", on_click=lambda: resolve("leave_unassigned")).props("flat no-caps")
                    with ui.row().classes("gap-2"):
                        ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                        ui.button("Create and file", icon="person_add", on_click=lambda: resolve("create_person")).props("outline no-caps")
                        ui.button("File with client", icon="assignment_turned_in", on_click=lambda: resolve("assign_existing")).props("no-caps")
            dialog.open()

        def refresh_workspace() -> None:
            refresh_metrics()
            refresh_packets()
            refresh_detached()
            refresh_reviews()

        refresh_button.on_click(refresh_workspace)
        refresh_workspace()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Homesteader workspace")
    parser.add_argument("--state", type=Path, default=Path("data/homesteader.json"))
    parser.add_argument("--inbox", type=Path, default=Path("inbox"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    build_workspace(HomesteaderStore(args.state), args.inbox)
    port = find_available_port(args.port)
    print(f"Homesteader is available locally at http://{LOCAL_HOST}:{port}")
    ui.run(host=LOCAL_HOST, port=port, title="Homesteader", reload=False, show=True)


if __name__ in {"__main__", "__mp_main__"}:
    main()
