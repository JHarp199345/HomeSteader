"""Local-only workspace for packet intake and human review."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import json
from pathlib import Path
import socket
import subprocess
import sys
from uuid import uuid4

from nicegui import app, background_tasks, ui

from homesteader.audit import filter_correction_findings
from homesteader.correction_export import export_correction_report
from homesteader.core import HomesteaderStore, SUPPORTED_INTAKE_SUFFIXES
from homesteader.inbox import inspect_inbox


LOCAL_HOST = "127.0.0.1"


def local_path(value: str) -> Path:
    """Accept a normal shell-style path without resolving it through a network service."""
    return Path(value).expanduser()


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
    archive_dir = store.path.parent / "sources"
    archive_dir.mkdir(parents=True, exist_ok=True)
    # This route exists only inside the loopback-only workspace. It exposes
    # original scans to the local browser UI, never to the network.
    app.add_static_files("/homesteader-source", archive_dir)
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
            with ui.column().classes("gap-0"):
                ui.label("Intake packets").classes("text-2xl font-semibold")
                ui.label(f"Scan folder: {inbox_path}").classes("text-sm muted break-all")
            refresh_button = ui.button(icon="refresh").props("flat round").tooltip("Refresh workspace")

        metrics = ui.row().classes("w-full gap-3 flex-wrap")
        packet_panel = ui.column().classes("panel w-full gap-3")
        review_panel = ui.column().classes("panel w-full gap-3")
        correction_panel = ui.column().classes("panel w-full gap-3")
        queue_panel = ui.column().classes("panel w-full gap-3")
        detached_panel = ui.column().classes("panel w-full gap-3")
        relationship_panel = ui.column().classes("panel w-full gap-3")
        form_bank_panel = ui.column().classes("panel w-full gap-3")
        participant_panel = ui.column().classes("panel w-full gap-3")

        selected_packet_id: str | None = None
        queue_worker_active = False
        participant_filters = {"query": "", "status": "all", "program": None, "has_lease": False, "date_from": None, "date_to": None}
        correction_filters = {"query": "", "caseworker": None, "program": None, "category": None, "date_from": None, "date_to": None}

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
                    upload = ui.upload(label="Add documents", multiple=True, auto_upload=True).props('accept=".pdf,.txt,.png,.jpg,.jpeg,.heic,.tif,.tiff"')
                    upload.on_upload(receive_packet_upload)
                    with ui.row().classes("gap-2 flex-wrap"):
                        ui.button("Queue new scans", icon="playlist_add", on_click=process_new_scans).props("outline no-caps")
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
                jobs = store.queue_intake_sources(packet["id"], [destination])
                store.save()
            except ValueError as error:
                ui.notify(str(error), type="negative")
                return
            start_intake_worker()
            ui.notify(f"Queued {event.name} for local processing." if jobs else f"{event.name} is already waiting to be processed.", type="positive")
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
            known_hashes = {document["sha256"] for document in store.data["documents"]}
            sources = [
                item.path for item in inspect_inbox(inbox_path)
                if item.path.suffix.casefold() in SUPPORTED_INTAKE_SUFFIXES and item.sha256 not in known_hashes
            ]
            jobs = store.queue_intake_sources(packet["id"], sources)
            store.save()
            start_intake_worker()
            if jobs:
                ui.notify(f"Queued {len(jobs)} new scan{'s' if len(jobs) != 1 else ''} for local processing.", type="positive")
            else:
                ui.notify("No new scans found.")
            refresh_workspace()

        async def run_intake_worker() -> None:
            nonlocal queue_worker_active
            try:
                while True:
                    job = store.claim_next_intake_job()
                    if not job:
                        store.save()
                        return
                    store.save()
                    try:
                        result = await asyncio.to_thread(store.add_to_intake_packet, job["packet_id"], [Path(job["source_path"])])
                        document_ids = [entry["result"].get("document_id") for entry in result["results"] if entry["result"].get("document_id")]
                        enriched = await asyncio.to_thread(auto_queue_scan_proposals, document_ids)
                        store.finish_intake_job(job["id"], result={"intake": result, "local_vision_proposals": enriched})
                    except Exception as error:  # A bad scan must fail one job, not the whole backlog.
                        store.finish_intake_job(job["id"], error=str(error))
                    store.save()
            finally:
                queue_worker_active = False

        def start_intake_worker() -> None:
            nonlocal queue_worker_active
            if queue_worker_active:
                return
            queue_worker_active = True
            background_tasks.create(run_intake_worker(), name="homesteader-intake-queue")

        def refresh_intake_queue() -> None:
            queue_panel.clear()
            with queue_panel:
                counts = store.intake_job_counts()
                ui.label("Local processing queue").classes("text-lg font-semibold")
                ui.label(f"Waiting: {counts['waiting']} · Processing: {counts['processing']} · Completed: {counts['completed']} · Needs attention: {counts['failed']}").classes("text-sm muted")
                failed = [job for job in store.data["intake_jobs"] if job.get("status") == "failed"][-3:]
                for job in failed:
                    ui.label(f"{job['source_name']}: {job.get('error', 'Could not process this scan.')}").classes("text-sm text-amber-800")

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
                categories = {}
                for review in reviews:
                    category = review.get("category", "other_review")
                    categories[category] = categories.get(category, 0) + 1
                if categories:
                    ui.label(" · ".join(f"{label.replace('_', ' ')}: {count}" for label, count in sorted(categories.items()))).classes("text-sm muted")
                for review in reviews[:12]:
                    document = next((item for item in store.data["documents"] if item["id"] == review["document_id"]), None)
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(document["original_name"] if document else "Document review").classes("font-medium text-sm")
                            ui.label(review.get("category", "other_review").replace("_", " ").title()).classes("text-xs text-amber-800")
                            ui.label(review["reason"]).classes("text-sm muted")
                        ui.button("Review", icon="fact_check", on_click=lambda review=review: open_review_dialog(review)).props("outline no-caps")

        def refresh_correction_findings() -> None:
            correction_panel.clear()
            with correction_panel:
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0"):
                        ui.label("Correction findings").classes("text-lg font-semibold")
                        ui.label("Evidence-backed issues to resolve or include in the local correction report.").classes("text-sm muted")
                    with ui.row().classes("gap-1"):
                        ui.button(icon="filter_list", on_click=open_correction_filters).props("flat round").tooltip("Filter correction findings")
                        ui.label("Local audit").classes("text-sm muted")
                findings = filter_correction_findings(store.correction_findings(), **correction_filters)
                if not findings:
                    ui.label("No correction findings match the current filters." if any(correction_filters.values()) else "No active correction findings.").classes("muted")
                    return
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(f"{len(findings)} finding{'s' if len(findings) != 1 else ''} shown").classes("text-sm muted")
                    with ui.row().classes("gap-2"):
                        ui.button("View report", icon="summarize", on_click=lambda findings=findings: open_correction_report(findings)).props("outline no-caps")
                        ui.button("Export XLSX", icon="download", on_click=lambda findings=findings: download_correction_report(findings)).props("outline no-caps")
                for finding in findings[:8]:
                    with ui.card().classes("w-full border border-slate-200 shadow-none"):
                        with ui.row().classes("w-full items-start justify-between"):
                            with ui.column().classes("gap-1"):
                                ui.label(f"{finding['ptc']} · {finding['category']}").classes("font-medium text-sm")
                                if finding["document"]:
                                    ui.label(finding["document"]).classes("text-sm muted")
                                if finding.get("program") or finding.get("finding_date"):
                                    ui.label(" · ".join(part for part in [finding.get("program"), finding.get("finding_date")] if part)).classes("text-xs muted")
                                ui.label(finding["error"]).classes("text-sm")
                                ui.label(f"Recommended: {finding['recommendation']}").classes("text-sm text-teal-800")
                            if finding["document_id"]:
                                ui.button(icon="visibility", on_click=lambda document_id=finding["document_id"]: open_document_viewer(document_id)).props("flat dense round").tooltip("View stored source")

        def open_correction_filters() -> None:
            all_findings = store.correction_findings()
            caseworkers = sorted({item["caseworker"] for item in all_findings if item.get("caseworker")})
            programs = sorted({item["program"] for item in all_findings if item.get("program")})
            categories = sorted({item["category"] for item in all_findings if item.get("category")})
            with ui.dialog() as dialog, ui.card().classes("w-96"):
                ui.label("Filter correction findings").classes("text-lg font-semibold")
                ui.label("Filters only change this local report view and its export.").classes("text-sm muted")
                query = ui.input("PTC, HMIS ID, document, or issue", value=correction_filters["query"]).classes("w-full")
                caseworker = ui.select(["All caseworkers", *caseworkers], value=correction_filters["caseworker"] or "All caseworkers", label="Caseworker").classes("w-full")
                program = ui.select(["All programs", *programs], value=correction_filters["program"] or "All programs", label="Program").classes("w-full")
                category = ui.select(["All error types", *categories], value=correction_filters["category"] or "All error types", label="Error type").classes("w-full")
                date_from = ui.input("Finding date from (YYYY-MM-DD)", value=correction_filters["date_from"] or "").classes("w-full")
                date_to = ui.input("Finding date to (YYYY-MM-DD)", value=correction_filters["date_to"] or "").classes("w-full")

                def clear() -> None:
                    correction_filters.update({"query": "", "caseworker": None, "program": None, "category": None, "date_from": None, "date_to": None})
                    dialog.close()
                    refresh_correction_findings()

                def apply() -> None:
                    correction_filters.update({
                        "query": query.value or "", "caseworker": None if caseworker.value == "All caseworkers" else caseworker.value,
                        "program": None if program.value == "All programs" else program.value,
                        "category": None if category.value == "All error types" else category.value,
                        "date_from": date_from.value or None, "date_to": date_to.value or None,
                    })
                    dialog.close()
                    refresh_correction_findings()

                with ui.row().classes("w-full justify-between"):
                    ui.button("Clear", on_click=clear).props("flat no-caps")
                    ui.button("Apply filters", on_click=apply).props("no-caps")
            dialog.open()

        def open_correction_report(findings: list[dict]) -> None:
            with ui.dialog() as dialog, ui.card().classes("w-[66rem] max-w-full"):
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0"):
                        ui.label("Correction report").classes("text-xl font-semibold")
                        ui.label(f"{len(findings)} filtered local finding{'s' if len(findings) != 1 else ''}").classes("text-sm muted")
                    ui.button(icon="close", on_click=dialog.close).props("flat round")
                for finding in findings:
                    with ui.card().classes("w-full border border-slate-200 shadow-none"):
                        ui.label(f"{finding['ptc']} · {finding['category']}").classes("font-medium")
                        details = [finding.get("participant_identifier"), finding.get("caseworker"), finding.get("program"), finding.get("finding_date")]
                        ui.label(" · ".join(detail for detail in details if detail)).classes("text-sm muted")
                        if finding.get("document"):
                            ui.label(f"Document: {finding['document']}").classes("text-sm muted")
                        ui.label(f"Reported error: {finding['error']}").classes("text-sm")
                        ui.label(f"Recommended correction: {finding['recommendation']}").classes("text-sm text-teal-800")
                        ui.label(f"Evidence source: {finding['source']}").classes("text-xs muted")
                        if finding.get("document_id"):
                            ui.button("View source", icon="visibility", on_click=lambda document_id=finding["document_id"]: open_document_viewer(document_id)).props("flat no-caps")
            dialog.open()

        def download_correction_report(findings: list[dict]) -> None:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
            output_path = store.path.parent / "reports" / f"Homesteader_Correction_Report_{timestamp}.xlsx"
            try:
                export_correction_report(findings, output_path)
            except RuntimeError as error:
                ui.notify(str(error), type="negative")
                return
            ui.download(output_path, filename=output_path.name)
            ui.notify(f"Local correction report created with {len(findings)} finding{'s' if len(findings) != 1 else ''}.", type="positive")

        def refresh_relationship_search() -> None:
            relationship_panel.clear()
            with relationship_panel:
                ui.label("Relationship search").classes("text-lg font-semibold")
                ui.label("Search canonical names and confirmed aliases to find connected participant files. Similar names are never silently merged.").classes("text-sm muted")
                query = ui.input("Landlord or property name").classes("w-full")
                results = ui.column().classes("w-full gap-2")

                def run_search() -> None:
                    results.clear()
                    matches = store.relationship_search(query.value or "")
                    entities = store.entity_directory_search(query.value or "")
                    with results:
                        if not (query.value or "").strip():
                            ui.label("Enter a landlord or property name.").classes("text-sm muted")
                        elif not entities:
                            ui.label("No participant files are linked to that recorded entity yet.").classes("text-sm muted")
                        else:
                            ui.label("Canonical entities and confirmed aliases").classes("text-sm font-medium")
                            for entity in entities:
                                with ui.row().classes("w-full items-center justify-between"):
                                    with ui.column().classes("gap-0"):
                                        ui.label(f"{entity['name']} ({entity['kind'].replace('_', ' ')})").classes("text-sm")
                                        if entity["aliases"]:
                                            ui.label("Aliases: " + ", ".join(entity["aliases"])).classes("text-xs muted")
                                    ui.button("Add alias", icon="alternate_email", on_click=lambda entity=entity: open_alias_dialog(entity)).props("flat no-caps")
                            if matches:
                                ui.label("Connected participant files").classes("text-sm font-medium mt-2")
                            for match in matches:
                                identifier = match["hmis_id"] or match["temporary_id"] or "No identifier yet"
                                with ui.row().classes("w-full items-center justify-between"):
                                    ui.label(f"{match['name']} — {identifier} · linked through {match['relationship_distance']} recorded relationship step(s)").classes("text-sm")
                                    ui.button("Open file", icon="folder_open", on_click=lambda person_id=match["person_id"]: open_participant_file(person_id)).props("flat no-caps")

                ui.button("Search relationships", icon="account_tree", on_click=run_search).props("outline no-caps")

        def open_alias_dialog(entity: dict) -> None:
            with ui.dialog() as dialog, ui.card().classes("w-96"):
                ui.label(f"Add alias for {entity['name']}").classes("text-lg font-semibold")
                ui.label("This creates another reliable search name for this one entity. It does not merge similarly named landlords, properties, or people.").classes("text-sm muted")
                alias = ui.input("Confirmed alternate name").classes("w-full")
                note = ui.input("Optional confirmation note").classes("w-full")

                def save_alias() -> None:
                    try:
                        store.add_entity_alias(entity["entity_id"], alias.value or "", note=note.value or None)
                        store.save()
                    except ValueError as error:
                        ui.notify(str(error), type="negative")
                        return
                    dialog.close()
                    ui.notify("Confirmed alias saved.", type="positive")
                    refresh_workspace()

                with ui.row().classes("w-full justify-end"):
                    ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                    ui.button("Save alias", on_click=save_alias).props("no-caps")
            dialog.open()

        def refresh_form_bank() -> None:
            form_bank_panel.clear()
            with form_bank_panel:
                ui.label("Form Bank").classes("text-lg font-semibold")
                ui.label("Reusable blank forms stay here, not in a participant file.").classes("text-sm muted")
                forms = [entity for entity in store.data["entities"] if entity["kind"] == "form_template"]
                if not forms:
                    ui.label("No reusable forms cataloged yet.").classes("text-sm muted")
                for form in forms:
                    event = next((entry for entry in reversed(store.data["ledger_events"]) if entry["type"] == "form_cataloged" and entry["subject_id"] == form["id"]), None)
                    document_id = event.get("details", {}).get("document_id") if event else None
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label(form["name"]).classes("text-sm")
                        if document_id:
                            ui.button(icon="visibility", on_click=lambda document_id=document_id: open_document_viewer(document_id)).props("flat dense round").tooltip("View stored form")

        def refresh_participant_index() -> None:
            participant_panel.clear()
            with participant_panel:
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0"):
                        ui.label("Participant files").classes("text-lg font-semibold")
                        ui.label("A compact working index, not a dashboard.").classes("text-sm muted")
                    ui.button(icon="filter_list", on_click=open_participant_filters).props("flat round").tooltip("Filter participant files")
                search = ui.input("Find a PTC", value=participant_filters["query"]).classes("w-full")

                def update_query() -> None:
                    participant_filters["query"] = search.value or ""
                    refresh_participant_index()

                search.on("keydown.enter", update_query)
                rows = store.participant_index(**participant_filters)
                ui.label(f"{len(rows)} participant file{'s' if len(rows) != 1 else ''}").classes("text-sm muted")
                if not rows:
                    ui.label("No participant files match the current search and filters.").classes("text-sm muted")
                for row in rows[:30]:
                    identifier = row["identifier"] or "No identifier yet"
                    programs = ", ".join(row["programs"]) or "No program recorded"
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(f"{row['name']} — {identifier}").classes("text-sm font-medium")
                            ui.label(f"{row['document_count']} document(s) · {row['lease_count']} lease(s) · {programs}").classes("text-sm muted")
                        ui.button("Open file", icon="folder_open", on_click=lambda person_id=row["person_id"]: open_participant_file(person_id)).props("flat no-caps")

        def open_participant_filters() -> None:
            program_names = sorted(entity["name"] for entity in store.data["entities"] if entity["kind"] == "program")
            with ui.dialog() as dialog, ui.card().classes("w-96"):
                ui.label("Filter participant files").classes("text-lg font-semibold")
                status = ui.select({"all": "All files", "confirmed": "HMIS-confirmed", "temporary": "Temporary"}, value=participant_filters["status"], label="Identity status").classes("w-full")
                program = ui.select(["All programs", *program_names], value=participant_filters["program"] or "All programs", label="Program").classes("w-full")
                lease_only = ui.checkbox("Has a recorded lease", value=participant_filters["has_lease"])
                date_from = ui.input("Document date from (YYYY-MM-DD)", value=participant_filters["date_from"] or "").classes("w-full")
                date_to = ui.input("Document date to (YYYY-MM-DD)", value=participant_filters["date_to"] or "").classes("w-full")
                with ui.row().classes("w-full justify-between"):
                    def clear() -> None:
                        participant_filters.update({"status": "all", "program": None, "has_lease": False, "date_from": None, "date_to": None})
                        dialog.close()
                        refresh_participant_index()

                    def apply() -> None:
                        participant_filters.update({
                            "status": status.value, "program": None if program.value == "All programs" else program.value,
                            "has_lease": lease_only.value, "date_from": date_from.value or None, "date_to": date_to.value or None,
                        })
                        dialog.close()
                        refresh_participant_index()

                    ui.button("Clear", on_click=clear).props("flat no-caps")
                    ui.button("Apply filters", on_click=apply).props("no-caps")
            dialog.open()

        def open_review_dialog(review: dict) -> None:
            document = next((item for item in store.data["documents"] if item["id"] == review["document_id"]), None)
            proposed = review.get("proposed_person_id")
            proposed_name = document["extracted"].get("participant") if document else ""
            with ui.dialog() as dialog, ui.card().classes("w-[42rem] max-w-full"):
                ui.label("Review document").classes("text-lg font-semibold")
                ui.label(document["original_name"] if document else "Document").classes("text-sm muted")
                ui.label(review["reason"]).classes("text-sm")
                if review.get("revision_of_document_id"):
                    original = next((item for item in store.data["documents"] if item["id"] == review["revision_of_document_id"]), None)
                    ui.label(f"Possible completed revision of: {original['original_name'] if original else 'stored original'}").classes("text-sm text-teal-800")
                    ui.label(f"New fields: {', '.join(review.get('revision_fields', []))}").classes("text-sm muted")
                if document and document.get("source_text"):
                    ui.textarea("Source text", value=document["source_text"][:3000]).props("readonly").classes("w-full")
                ui.label("Find the participant file").classes("font-medium")
                ui.label("Search by the name on this document. Open a match to inspect its existing evidence before filing.").classes("text-sm muted")
                search = ui.input("Participant name", value=proposed_name or "").classes("w-full")
                selected_person_id: str | None = proposed
                selected_label = ui.label("No participant file selected.").classes("text-sm muted")
                match_results = ui.column().classes("w-full gap-2")

                def select_person(person_id: str) -> None:
                    nonlocal selected_person_id
                    summary = store.participant_file(person_id)
                    selected_person_id = person_id
                    identifier = summary["attributes"].get("hmis_id") or summary["attributes"].get("temporary_id") or "No identifier yet"
                    selected_label.set_text(f"Selected: {summary['name']} — {identifier}")
                    selected_label.classes(remove="muted")

                def show_matches() -> None:
                    match_results.clear()
                    matches = store.search_files(search.value or "")
                    with match_results:
                        if not (search.value or "").strip():
                            ui.label("Enter a name to search existing participant files.").classes("text-sm muted")
                        elif not matches:
                            ui.label("No existing participant file matches this name. You can create a provisional file below.").classes("text-sm muted")
                        for match in matches:
                            summary = store.participant_file(match["person_id"])
                            identifier = match["hmis_id"] or match["temporary_id"] or "No identifier yet"
                            with ui.card().classes("w-full border border-slate-200 shadow-none"):
                                with ui.row().classes("w-full items-center justify-between"):
                                    with ui.column().classes("gap-0"):
                                        ui.label(f"{match['name']} — {match['status']}").classes("font-medium")
                                        ui.label(f"{identifier} · {match['document_count']} linked document(s) · {summary['event_count']} recorded event(s)").classes("text-sm muted")
                                    ui.button("Use this file", on_click=lambda person_id=match["person_id"]: select_person(person_id)).props("outline no-caps")
                                if summary["documents"]:
                                    ui.label("Existing evidence:").classes("text-sm font-medium mt-2")
                                    for linked in summary["documents"][-5:]:
                                        detail = linked["document_type"].replace("_", " ")
                                        if linked.get("reporting_period"):
                                            detail += f" · {linked['reporting_period']}"
                                        elif linked.get("document_date"):
                                            detail += f" · {linked['document_date']}"
                                        with ui.row().classes("items-center gap-1"):
                                            ui.label(f"• {linked['original_name']} ({detail})").classes("text-sm muted")
                                            ui.button(icon="visibility", on_click=lambda document_id=linked["id"]: open_document_viewer(document_id)).props("flat dense round").tooltip("View stored source")

                ui.button("Search files", icon="search", on_click=show_matches).props("outline no-caps")
                show_matches()
                new_name = ui.input("Or create provisional client", value=proposed_name or "").classes("w-full")
                context_note = ui.textarea("What is this connected to?", placeholder="Example: Water damage on the bedroom wall in Unit 1 at Harbor View, reported by Jasmine Morales today. You can type or use Mac dictation.").classes("w-full")
                note = ui.textarea("Decision note").classes("w-full")

                def resolve(action: str) -> None:
                    try:
                        if action == "assign_existing":
                            store.resolve_review(review["id"], action, entity_id=selected_person_id, note=note.value or None, context_note=context_note.value or None)
                        elif action == "create_person":
                            store.resolve_review(review["id"], action, new_person_name=new_name.value or None, note=note.value or None, context_note=context_note.value or None)
                        elif action == "catalog_form":
                            store.resolve_review(review["id"], action, note=note.value or None, context_note=context_note.value or None)
                        else:
                            store.resolve_review(review["id"], action, note=note.value or None, context_note=context_note.value or None)
                        store.save()
                    except ValueError as error:
                        ui.notify(str(error), type="negative")
                        return
                    dialog.close()
                    ui.notify("Review recorded.", type="positive")
                    refresh_workspace()

                with ui.row().classes("w-full justify-between flex-wrap"):
                    with ui.row().classes("gap-2"):
                        ui.button("Leave unassigned", on_click=lambda: resolve("leave_unassigned")).props("flat no-caps")
                        ui.button("Store in Form Bank", icon="inventory_2", on_click=lambda: resolve("catalog_form")).props("flat no-caps")
                    with ui.row().classes("gap-2"):
                        ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                        if review.get("revision_of_document_id"):
                            ui.button("Confirm completed revision", icon="published_with_changes", on_click=lambda: resolve("accept_revision")).props("outline no-caps")
                        ui.button("Create and file", icon="person_add", on_click=lambda: resolve("create_person")).props("outline no-caps")
                        ui.button("File with client", icon="assignment_turned_in", on_click=lambda: resolve("assign_existing")).props("no-caps")
            dialog.open()

        def open_document_viewer(document_id: str) -> None:
            document = next((item for item in store.data["documents"] if item["id"] == document_id), None)
            if not document:
                ui.notify("The stored document could not be found.", type="negative")
                return
            stored_path = document.get("stored_source_path")
            source_url = f"/homesteader-source/{Path(stored_path).name}" if stored_path else None
            with ui.dialog() as dialog, ui.card().classes("w-[54rem] max-w-full"):
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0"):
                        ui.label(document["original_name"]).classes("text-lg font-semibold")
                        ui.label(f"{document.get('source_format', 'unknown').upper()} · {document.get('source_size_bytes', 0):,} bytes").classes("text-sm muted")
                    ui.button(icon="close", on_click=dialog.close).props("flat round")
                if source_url:
                    with ui.row().classes("items-center gap-2"):
                        ui.link("Open archived original in a new local tab", source_url, new_tab=True).classes("text-primary")
                        if document.get("source_format", "").casefold() in {"pdf", "png", "jpg", "jpeg", "heic", "tif", "tiff"}:
                            ui.button("Re-run local scan reader", icon="document_scanner", on_click=lambda: open_local_vision_dialog(document_id)).props("outline no-caps")
                else:
                    ui.label("This older record has no archived original; the extracted text is still available below.").classes("text-sm text-amber-800")
                proposals = [proposal for proposal in store.data.get("ai_proposals", []) if proposal.get("proposal", {}).get("document_id") == document_id]
                if proposals:
                    ui.label("Local AI proposals (review-only)").classes("font-medium mt-2")
                    for proposal in proposals:
                        detail = proposal["proposal"]
                        ui.label(f"{detail['provider_id']} · {detail['document_type']} · {proposal['status']}").classes("text-sm")
                        if detail.get("uncertainties"):
                            ui.label("Uncertainties: " + "; ".join(detail["uncertainties"])).classes("text-xs text-amber-800")
                if document.get("context_annotations"):
                    ui.label("User-provided context").classes("font-medium mt-2")
                    for annotation in document["context_annotations"]:
                        ui.label(annotation["text"]).classes("text-sm")
                ui.label("Extracted text / local OCR").classes("font-medium mt-2")
                ui.textarea(value=document.get("source_text", "")).props("readonly").classes("w-full").style("min-height: 24rem")
            dialog.open()

        def queue_local_vision_proposal(document_id: str, model_name: str = "gemma4:12b") -> dict:
            """Stage one preserved scan to local Ollama and queue its review-only output."""
            document = next((item for item in store.data["documents"] if item["id"] == document_id), None)
            if not document or not document.get("stored_source_path"):
                raise ValueError("The original scan is not available for local vision review.")
            source = store.path.parent / document["stored_source_path"]
            if not source.exists():
                raise ValueError("The archived source scan is missing.")
            staging = store.path.parent / "ai_staging"
            staging.mkdir(parents=True, exist_ok=True)
            output = staging / f"vision-proposal-{document_id}.json"
            script = Path(__file__).resolve().parents[1] / "tools" / "local_vision_propose.py"
            command = [sys.executable, str(script), str(source), "--document-id", document_id, "--model", model_name, "--provider", "ollama", "--output", str(output)]
            try:
                completed = subprocess.run(command, capture_output=True, text=True, timeout=240, check=False)
            except subprocess.TimeoutExpired as error:
                raise ValueError("The local vision model did not finish within four minutes.") from error
            if completed.returncode != 0:
                raise ValueError((completed.stderr or completed.stdout or "Local vision proposal failed.").strip()[:500])
            record = store.submit_ai_proposal(json.loads(output.read_text()))
            store.save()
            return record

        def auto_queue_scan_proposals(document_ids: list[str]) -> int:
            """Use scan characteristics, never a user-selected 'handwriting' label.

            A document that had no embedded text and needed local OCR is a scan
            requiring visual interpretation.  The local model may improve its
            transcription, but its proposal remains review-only.
            """
            queued = 0
            known_proposals = {item.get("proposal", {}).get("document_id") for item in store.data.get("ai_proposals", [])}
            for document_id in document_ids:
                document = next((item for item in store.data["documents"] if item["id"] == document_id), None)
                if not document or document_id in known_proposals:
                    continue
                if document.get("text_extraction", {}).get("method") != "macos_vision_ocr":
                    continue
                try:
                    queue_local_vision_proposal(document_id)
                    queued += 1
                except ValueError as error:
                    self_event = {"document_id": document_id, "reason": str(error), "source": "automatic_local_scan_reader"}
                    store._event("local_vision_proposal_failed", document_id, self_event)
                    store.save()
            return queued

        def open_local_vision_dialog(document_id: str) -> None:
            document = next((item for item in store.data["documents"] if item["id"] == document_id), None)
            if not document or not document.get("stored_source_path"):
                ui.notify("The original scan is not available for local vision review.", type="warning")
                return
            with ui.dialog() as dialog, ui.card().classes("w-[34rem] max-w-full"):
                ui.label("Read handwriting locally").classes("text-lg font-semibold")
                ui.label("Homesteader will send only this preserved scan to a model running on this Mac. The result becomes a review-only proposal; it cannot file or change the participant record.").classes("text-sm muted")
                model = ui.input("Local Ollama vision model", value="gemma4:12b").classes("w-full")

                def stage() -> None:
                    try:
                        record = queue_local_vision_proposal(document_id, model.value or "gemma4:12b")
                    except (OSError, ValueError, json.JSONDecodeError) as error:
                        ui.notify(f"The proposal could not be queued: {error}", type="negative")
                        return
                    dialog.close()
                    ui.notify(f"Local vision proposal queued for review ({record['status']}).", type="positive")
                    refresh_workspace()

                with ui.row().classes("w-full justify-end"):
                    ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                    ui.button("Create review proposal", icon="document_scanner", on_click=stage).props("no-caps")
            dialog.open()

        def open_participant_file(person_id: str) -> None:
            summary = store.participant_file(person_id)
            attributes = summary["attributes"]
            identifier = attributes.get("hmis_id") or attributes.get("temporary_id") or "No identifier yet"
            schedule_items = [item for item in store.housing_schedule_status() if item["person_id"] == person_id]
            move_in_items = [item for item in store.move_in_workflow_status() if item["participant_id"] == person_id]
            with ui.dialog() as dialog, ui.card().classes("w-[60rem] max-w-full"):
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0"):
                        ui.label(summary["name"]).classes("text-xl font-semibold")
                        ui.label(f"{summary['status'].title()} file · {identifier}").classes("text-sm muted")
                    ui.button(icon="close", on_click=dialog.close).props("flat round")
                with ui.row().classes("w-full gap-6 flex-wrap"):
                    with ui.column().classes("gap-1 min-w-[16rem]"):
                        ui.label("Recorded relationships").classes("font-medium")
                        if not summary["related_entities"]:
                            ui.label("No related entities recorded yet.").classes("text-sm muted")
                        for related in summary["related_entities"]:
                            path = " → ".join(part.replace("_", " ") for part in related["path"])
                            ui.label(f"{related['name']} ({related['kind'].replace('_', ' ')})").classes("text-sm")
                            ui.label(path).classes("text-xs muted ml-2")
                    with ui.column().classes("gap-1 flex-grow"):
                        ui.label("Evidence documents").classes("font-medium")
                        if not summary["documents"]:
                            ui.label("No documents are linked to this file yet.").classes("text-sm muted")
                        for document in summary["documents"]:
                            with ui.row().classes("items-center gap-1"):
                                ui.label(document["original_name"]).classes("text-sm")
                                ui.button(icon="visibility", on_click=lambda document_id=document["id"]: open_document_viewer(document_id)).props("flat dense round").tooltip("View stored source")
                if schedule_items:
                    ui.label("Program timeline").classes("font-medium mt-3")
                    for item in schedule_items:
                        state = "Documented" if item["status"] == "documented" else "Missing"
                        ui.label(f"{item['due_date']} · {item['requirement'].title()} · {state}").classes(
                            "text-sm text-teal-800" if item["status"] == "documented" else "text-sm text-amber-800"
                        )
                    ui.label(f"Standard end date: {schedule_items[0]['standard_end_date']} (exceptions must be recorded separately)").classes("text-xs muted")
                if move_in_items:
                    ui.label("Move-in workflows").classes("font-medium mt-3")
                    for item in move_in_items:
                        present = ", ".join(value.replace("_", " ") for value in item["present_record_types"])
                        missing = ", ".join(value.replace("_", " ") for value in item["missing_record_types"])
                        state_class = "text-amber-800" if item["status"] == "needs_review" else "text-teal-800"
                        ui.label(f"{item['status'].replace('_', ' ').title()} · present: {present or 'none'}").classes(f"text-sm {state_class}")
                        if missing:
                            ui.label(f"Still expected for local review: {missing}").classes("text-sm text-amber-800")
                        for conflict in item.get("conflicts", []):
                            values = " / ".join(conflict["values"])
                            ui.label(f"Review conflict: {conflict['field'].replace('_', ' ')} — {values}").classes("text-sm text-amber-800")
                ui.label("Ledger history").classes("font-medium mt-3")
                if not summary["events"]:
                    ui.label("No events recorded yet.").classes("text-sm muted")
                for event in summary["events"][:20]:
                    ui.label(f"{event['type'].replace('_', ' ')} · {event.get('recorded_at', '')}").classes("text-sm")
            dialog.open()

        def refresh_workspace() -> None:
            refresh_metrics()
            refresh_packets()
            refresh_detached()
            refresh_reviews()
            refresh_correction_findings()
            refresh_intake_queue()
            refresh_relationship_search()
            refresh_form_bank()
            refresh_participant_index()

        refresh_button.on_click(refresh_workspace)
        ui.timer(1.5, refresh_intake_queue)
        refresh_workspace()
        if store.intake_job_counts()["waiting"]:
            start_intake_worker()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Homesteader workspace")
    parser.add_argument("--state", type=local_path, default=Path("data/homesteader.json"))
    parser.add_argument(
        "--inbox",
        type=local_path,
        default=Path("inbox"),
        help="Local or iCloud Drive folder to inspect when 'Process new scans' is selected.",
    )
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    build_workspace(HomesteaderStore(args.state), args.inbox)
    port = find_available_port(args.port)
    print(f"Homesteader is available locally at http://{LOCAL_HOST}:{port}")
    ui.run(host=LOCAL_HOST, port=port, title="Homesteader", reload=False, show=True)


if __name__ in {"__main__", "__mp_main__"}:
    main()
