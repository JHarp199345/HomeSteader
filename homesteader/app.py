"""Local-only workspace for packet intake and human review."""

from __future__ import annotations

import argparse
import asyncio
import calendar as calendar_module
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import socket
import subprocess
import sys
from uuid import uuid4

from nicegui import app, background_tasks, ui

from homesteader.audit import filter_correction_findings
from homesteader.correction_export import export_correction_report
from homesteader.calendar_projection import EXPORTABLE_STATUSES, export_ics, schedule_calendar_events
from homesteader.core import HomesteaderStore, SUPPORTED_INTAKE_SUFFIXES, browse_kind_from_query
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
    # Older local states may predate the evidence-link invariant. Repair only
    # explicit, defensible links before rendering the workspace; the original
    # events and sources remain untouched.
    reconciliation = store.reconcile_document_evidence()
    if reconciliation["evidence_links_added"]:
        store.save()
    archive_dir = store.path.parent / "sources"
    exports_dir = store.path.parent / "exports"
    asset_dir = Path(__file__).resolve().parents[1] / "assets"
    archive_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)
    # This route exists only inside the loopback-only workspace. It exposes
    # original scans to the local browser UI, never to the network.
    app.add_static_files("/homesteader-source", archive_dir)
    app.add_static_files("/homesteader-export", exports_dir)
    if asset_dir.exists():
        app.add_static_files("/homesteader-assets", asset_dir)

    def render_preserved_source(document: dict, source_url: str, classes: str) -> None:
        """Render the archived original with a browser-native fallback.

        ``object`` handles PDFs more reliably than a nested browser frame on
        desktop Safari/Chromium, while images remain directly visible.  The
        link is intentionally retained so an operator can always inspect the
        preserved local source even if their browser disables inline PDFs.
        """
        suffix = Path(document.get("stored_source_path", "")).suffix.casefold()
        if suffix in {".png", ".jpg", ".jpeg", ".heic", ".tiff", ".webp"}:
            ui.image(source_url).classes(classes + " object-contain bg-white border-2 border-ink rounded-lg")
            return
        if suffix == ".pdf":
            ui.html(
                f'<object data="{source_url}" type="application/pdf" class="w-full h-full">'
                f'<p class="p-4">Inline PDF preview is unavailable. '
                f'<a href="{source_url}" target="_blank">Open the preserved local PDF.</a></p></object>'
            ).classes(classes + " border-2 border-ink rounded-lg bg-white overflow-hidden")
            return
        ui.html(f'<iframe src="{source_url}" class="w-full h-full border-0"></iframe>').classes(
            classes + " border-2 border-ink rounded-lg bg-white overflow-hidden"
        )
    ui.colors(primary="#1a7f7d", secondary="#d43a2c", accent="#d43a2c", positive="#1a7f7d", negative="#b83a2d")
    ui.add_head_html("""
        <style>
          @font-face {
            font-family: "Homesteader Script";
            src: url("/homesteader-assets/fonts/Lobster-Regular.ttf") format("truetype");
            font-style: normal;
            font-weight: 400;
            font-display: swap;
          }
          @font-face {
            font-family: "Homesteader Display";
            src: url("/homesteader-assets/fonts/Oswald-Variable.ttf") format("truetype");
            font-style: normal;
            font-weight: 200 700;
            font-display: swap;
          }
          :root {
            --ink: #1c1d1f;
            --cream: #fbf5e6;
            --cream-bright: #fdf7e7;
            --paper: #f2e9d6;
            --manila: #efe3c6;
            --red: #d43a2c;
            --teal: #1a7f7d;
          }
          body { background: var(--paper); color: var(--ink); font-family: Arial, Helvetica, sans-serif; }
          .page-shell { max-width: 1420px; margin: 0 auto; padding: 22px 30px 46px; }
          .muted { color: #6e6a58; }
          .display-label { font-family: "Homesteader Display", sans-serif; font-weight: 500; letter-spacing: .04em; }
          .section-kicker { color: var(--red); font-family: "Homesteader Display", sans-serif; font-weight: 600; letter-spacing: .12em; text-transform: uppercase; font-size: .82rem; }
          .view-heading { font-family: "Homesteader Display", sans-serif; font-weight: 600; letter-spacing: .02em; text-transform: uppercase; }

          /* Ink-outline cards with offset print shadow */
          .panel { background: var(--cream); border: 2px solid var(--ink); border-radius: 14px; padding: 16px 18px; box-shadow: 6px 6px 0 rgba(28,29,31,.85); }
          .panel-bar { margin: -16px -18px 14px; width: calc(100% + 36px); border-radius: 11px 11px 0 0; border-bottom: 2px solid var(--ink); padding: 9px 18px; color: var(--cream-bright); display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
          .bar-teal { background: var(--teal); }
          .bar-red { background: var(--red); }
          .panel-bar .bar-title { font-family: "Homesteader Display", sans-serif; font-weight: 600; letter-spacing: .09em; text-transform: uppercase; font-size: 1.02rem; }
          .bar-btn { background: var(--cream-bright) !important; color: #123c3b !important; border: 2px solid rgba(28,29,31,.9); border-radius: 8px; }
          .bar-btn .q-btn__content { font-family: "Homesteader Display", sans-serif; text-transform: uppercase; letter-spacing: .06em; font-size: .74rem; }

          /* Masthead */
          .tagline-caps { font-family: "Homesteader Display", sans-serif; font-weight: 700; text-transform: uppercase; line-height: 1.04; letter-spacing: .015em; }
          .tagline-script { font-family: "Homesteader Script", cursive; color: var(--red); line-height: 1.1; }
          .starburst { color: var(--red); }
          .starburst-teal { color: var(--teal); }
          .search-anchor { background: var(--cream); border: 2px solid var(--ink); border-radius: 999px; padding: 6px 8px 6px 22px; box-shadow: 5px 5px 0 rgba(28,29,31,.85); }
          .search-anchor .q-field__control { background: transparent; }
          .search-anchor .q-field__control:before, .search-anchor .q-field__control:after { display: none; }
          .workspace-chip { background: var(--teal); color: var(--cream-bright); border: 2px solid var(--ink); border-radius: 12px; box-shadow: 5px 5px 0 rgba(28,29,31,.85); padding: 10px 18px; }

          /* Red filing-cabinet drawer */
          .app-drawer { background: var(--red); color: var(--cream-bright); border-right: 2px solid var(--ink); }
          .app-drawer .q-btn, .app-drawer .q-btn .q-btn__content, .app-drawer .q-btn .q-icon { color: var(--cream-bright) !important; border-radius: 8px; justify-content: flex-start; }
          .app-drawer .q-btn .q-btn__content { font-family: "Homesteader Display", sans-serif; font-weight: 500; letter-spacing: .07em; text-transform: uppercase; font-size: .82rem; }
          .app-drawer .q-btn:hover { background: rgba(28,29,31,.22); }
          .drawer-active { background: var(--cream-bright) !important; }
          .app-drawer .q-btn.drawer-active .q-btn__content, .app-drawer .q-btn.drawer-active .q-icon { color: var(--ink) !important; }
          .workspace-chip .tagline-script { color: var(--cream-bright); }
          .badge-circle { width: 108px; height: 108px; border-radius: 9999px; background: var(--cream-bright); border: 3px solid var(--ink); display: flex; align-items: center; justify-content: center; margin: 0 auto; box-shadow: 0 4px 0 rgba(28,29,31,.45); }
          .wordmark { font-family: "Homesteader Script", cursive; font-weight: 400; letter-spacing: -.02em; line-height: 1; }
          .scan-card { background: var(--teal); border: 2px solid var(--ink); border-radius: 10px; padding: 10px 12px; box-shadow: 3px 3px 0 rgba(28,29,31,.55); }

          /* Manila folder tabs */
          .tab-row { align-items: flex-end; gap: 7px; width: 100%; border-bottom: 3px solid var(--ink); padding: 0 8px; flex-wrap: nowrap; overflow-x: auto; }
          .folder-tab { background: var(--manila); border: 2px solid var(--ink); border-bottom: none; border-radius: 11px 11px 0 0; padding: 8px 16px 7px; cursor: pointer; color: #4a4536; white-space: nowrap; font-family: "Homesteader Display", sans-serif; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; font-size: .8rem; display: flex; align-items: center; gap: 6px; }
          .folder-tab:hover { background: #f6ecd2; color: var(--ink); }
          .tab-active-red { background: var(--red) !important; color: var(--cream-bright) !important; }
          .tab-active-teal { background: var(--teal) !important; color: var(--cream-bright) !important; }

          /* Directory browse chips */
          .browse-chip { background: var(--manila); border: 2px solid var(--ink); border-radius: 999px; padding: 3px 13px; cursor: pointer; display: flex; align-items: center; gap: 5px; font-family: "Homesteader Display", sans-serif; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; font-size: .72rem; color: #4a4536; }
          .browse-chip:hover { background: var(--teal); color: var(--cream-bright); }
          .browse-chip.upload-chip-teal { background: var(--teal) !important; color: var(--cream-bright) !important; border: 2px solid var(--ink); }
          .browse-chip.upload-chip-teal:hover { background: #0d5c58 !important; color: var(--cream-bright) !important; }


          /* Stat tiles */
          .stat-tile { background: var(--cream); border: 2px solid var(--ink); border-radius: 12px; box-shadow: 5px 5px 0 rgba(28,29,31,.85); padding: 13px 16px; display: flex; gap: 14px; align-items: center; flex: 1; min-width: 215px; }
          .stat-tile-red { background: var(--red); color: var(--cream-bright); }
          .stat-tile-red .muted { color: rgba(253,247,231,.85); }
          .icon-disc { min-width: 52px; width: 52px; height: 52px; border-radius: 9999px; background: var(--ink); color: var(--cream-bright); display: flex; align-items: center; justify-content: center; }
          .stat-number { font-family: "Homesteader Display", sans-serif; font-weight: 700; font-size: 2.35rem; line-height: 1; }
          .stat-teal-number { color: var(--teal); }
          .stat-label { font-family: "Homesteader Display", sans-serif; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; font-size: .8rem; }

          /* Dotted ledger leaders */
          .leader-row { display: flex; align-items: baseline; width: 100%; font-family: "Homesteader Display", sans-serif; font-weight: 500; letter-spacing: .04em; }
          .leader-dots { flex: 1 1 auto; margin: 0 8px; border-bottom: 3px dotted var(--ink); transform: translateY(-5px); }

          /* Retro buttons */
          .q-btn .q-btn__content { font-family: "Homesteader Display", sans-serif; letter-spacing: .05em; }
          .q-btn.retro-primary { background: var(--red) !important; color: var(--cream-bright) !important; border: 2px solid var(--ink); border-radius: 999px; box-shadow: 3px 3px 0 rgba(28,29,31,.85); padding: 4px 20px; }
          .q-btn.retro-primary .q-btn__content { text-transform: uppercase; font-weight: 600; }
          .q-btn.retro-secondary { background: var(--cream-bright) !important; color: var(--ink) !important; border: 2px solid var(--ink); border-radius: 999px; padding: 2px 16px; }
          .q-btn.retro-secondary .q-btn__content { text-transform: uppercase; font-weight: 600; }
          .q-btn.bar-btn { background: var(--cream-bright) !important; color: #123c3b !important; }
          .view-all { font-family: "Homesteader Display", sans-serif; font-weight: 600; color: var(--red); cursor: pointer; letter-spacing: .07em; text-transform: uppercase; text-align: center; width: 100%; font-size: .82rem; }
          .view-all:hover { text-decoration: underline; }

          /* Quick actions */
          .qa-circle { width: 62px; height: 62px; border-radius: 9999px; background: var(--red) !important; color: var(--cream-bright) !important; border: 2px solid var(--ink); box-shadow: 3px 3px 0 rgba(28,29,31,.85); }
          .qa-label { font-family: "Homesteader Display", sans-serif; font-weight: 600; font-size: .66rem; letter-spacing: .08em; text-transform: uppercase; text-align: center; }

          /* Dialogs on cream card stock */
          .q-dialog .q-card { background: var(--cream); border: 2px solid var(--ink); border-radius: 14px; box-shadow: 7px 7px 0 rgba(28,29,31,.6); }

          /* Local schedule calendar */
          .calendar-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); border-top: 2px solid var(--ink); border-left: 2px solid var(--ink); }
          .calendar-weekday { background: var(--teal); color: var(--cream-bright); border-right: 2px solid var(--ink); border-bottom: 2px solid var(--ink); padding: 6px; font-family: "Homesteader Display", sans-serif; font-weight: 600; letter-spacing: .06em; text-align: center; text-transform: uppercase; font-size: .72rem; }
          .calendar-day { min-height: 116px; border-right: 2px solid var(--ink); border-bottom: 2px solid var(--ink); background: var(--cream-bright); padding: 6px; overflow: hidden; }
          .calendar-day-muted { background: #e9dfc8; color: #766f60; }
          .calendar-day-number { font-family: "Homesteader Display", sans-serif; font-weight: 700; font-size: 1rem; }
          .calendar-event { border: 1px solid var(--ink); border-radius: 5px; padding: 3px 5px; margin-top: 4px; font-size: .68rem; line-height: 1.15; cursor: pointer; overflow: hidden; }
          .calendar-event-documented { background: #d6eee5; }
          .calendar-event-upcoming { background: #d8eceb; }
          .calendar-event-due { background: #ffe3a9; }
          .calendar-event-missing { background: #ffd2ca; }
          .calendar-month-card { min-height: 126px; background: var(--cream-bright); border: 2px solid var(--ink); border-radius: 8px; padding: 9px; box-shadow: 3px 3px 0 rgba(28,29,31,.45); cursor: pointer; }
          .calendar-month-card:hover { background: var(--manila); }
        </style>
    """)

    active_view = {"key": "files"}
    global_search = {"query": ""}
    nav_buttons: dict[str, object] = {}

    def handle_file_upload(e) -> None:
        """Stage a user-selected file locally without overwriting a prior scan."""
        try:
            content = e.content.read()
            filename = Path(getattr(e, "name", "uploaded_document.pdf")).name
            inbox_path.mkdir(parents=True, exist_ok=True)
            destination = inbox_path / f"upload-{uuid4()}-{filename}"
            destination.write_bytes(content)
            ui.notify(f"Staged '{filename}' locally. Homesteader will process it after the copy is stable.", type="positive")
            watch_intake_folder()
        except Exception as err:
            ui.notify(f"Upload error: {err}", type="negative")

    with ui.left_drawer(value=True).props("behavior=desktop bordered").classes("app-drawer p-4"):
        with ui.column().classes("w-full items-center gap-1 mb-6"):
            with ui.element("div").classes("badge-circle"):
                ui.element("img").props('src="/homesteader-assets/homesteader-cowboy.png"').style("height: 86px; width: auto; object-fit: contain; display: block;")
            ui.label("Homesteader").classes("wordmark text-4xl mt-2")
            ui.label("LOCAL WORKSPACE").classes("display-label text-[10px] tracking-widest opacity-90")
        ui.label("WORKSPACE").classes("display-label text-[10px] tracking-widest opacity-70 mb-1")
        for key, label, icon in [
            ("files", "Participant Files", "folder_open"), ("review", "Errors & Review", "warning"),
            ("overview", "Dashboard", "home"), ("reports", "Correction Reports", "summarize"),
            ("packets", "Packets & Intake", "inventory_2"), ("calendar", "Schedule", "calendar_month"),
        ]:
            nav_buttons[key] = ui.button(label, icon=icon, on_click=lambda key=key: set_active_view(key)).props("flat no-caps").classes("w-full mb-1")
        ui.separator().classes("my-3 opacity-30")
        ui.label("DATA").classes("display-label text-[10px] tracking-widest opacity-70 mb-1")
        nav_buttons["forms"] = ui.button("Form Bank", icon="article", on_click=lambda: set_active_view("forms")).props("flat no-caps").classes("w-full mb-1")
        with ui.column().classes("scan-card w-full gap-0 mt-6"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("folder", size="18px")
                ui.label("AUTO-WATCH FOLDER").classes("display-label text-[10px] tracking-widest")
            ui.label(str(inbox_path)).classes("text-xs opacity-90 break-all")

    with ui.column().classes("page-shell w-full gap-5"):
        with ui.row().classes("w-full items-center gap-6 flex-nowrap"):
            with ui.column().classes("gap-0 shrink-0"):
                ui.label("Find it. Connect it.").classes("tagline-caps text-3xl")
                ui.label("Keep it together.").classes("tagline-caps text-3xl")
                with ui.row().classes("items-center gap-2 flex-nowrap"):
                    ui.label("All in One Place.").classes("tagline-script text-3xl")
                    ui.label("✦").classes("starburst text-2xl")
            ui.element("div").classes("flex-grow")
            with ui.column().classes("workspace-chip gap-0 items-start shrink-0"):
                with ui.row().classes("items-center gap-2 flex-nowrap"):
                    ui.label("✦").classes("text-base")
                    ui.label("LOCAL WORKSPACE").classes("display-label text-sm tracking-widest")
                ui.label("This computer only").classes("tagline-script text-xl")

        relationship_panel = ui.column().classes("w-full gap-2")

        with ui.row().classes("tab-row flex-nowrap") as tab_bar:
            tab_elements: dict[str, object] = {}
            for key, label, icon in [
                ("files", "Participant Files", "folder_open"), ("review", "Needs Review", "warning"),
                ("reports", "Correction Findings", "summarize"), ("packets", "Packets & Intake", "inventory_2"),
                ("calendar", "Schedule", "calendar_month"), ("forms", "Form Bank", "article"),
            ]:
                with ui.element("div").classes("folder-tab") as tab:
                    ui.icon(icon, size="16px")
                    ui.label(label)
                tab.on("click", lambda key=key: set_active_view(key))
                tab_elements[key] = tab

        with ui.row().classes("items-center justify-between w-full"):
            with ui.column().classes("gap-0"):
                view_kicker = ui.label("WORKSPACE").classes("section-kicker")
                view_title = ui.label("Overview").classes("view-heading text-3xl font-semibold")
                view_subtitle = ui.label("What needs attention, locally and right now.").classes("text-sm muted")
            refresh_button = ui.button(icon="refresh", color=None).classes("retro-secondary").props("round").tooltip("Refresh workspace")

        metrics = ui.row().classes("w-full gap-4 flex-wrap")

        with ui.row().classes("w-full gap-5 flex-nowrap items-start"):
            with ui.column().classes("flex-grow min-w-0 gap-5"):
                packet_panel = ui.column().classes("panel w-full gap-3")
                review_panel = ui.column().classes("panel w-full gap-3")
                correction_panel = ui.column().classes("panel w-full gap-3")
                detached_panel = ui.column().classes("panel w-full gap-3")
                calendar_panel = ui.column().classes("panel w-full gap-3")
                form_bank_panel = ui.column().classes("panel w-full gap-3")
                participant_panel = ui.column().classes("panel w-full gap-3")
            with ui.column().classes("w-[22rem] shrink-0 gap-5") as right_rail:
                queue_panel = ui.column().classes("panel w-full gap-3")
                activity_panel = ui.column().classes("panel w-full gap-3")
                quick_actions_panel = ui.column().classes("panel w-full gap-3")

        with quick_actions_panel:
            with ui.row().classes("panel-bar bar-teal"):
                ui.label("Quick Actions").classes("bar-title")
            with ui.row().classes("w-full justify-around flex-nowrap"):
                for label, icon, action in [
                    ("New Packet", "note_add", lambda: open_new_packet_dialog()),
                    ("Import Files", "drive_folder_upload", lambda: set_active_view("packets")),
                    ("Export Report", "download", lambda: download_correction_report(
                        filter_correction_findings(store.correction_findings(), **correction_filters))),
                    ("Add Client", "person_add", lambda: set_active_view("review")),
                ]:
                    with ui.column().classes("items-center gap-1"):
                        ui.button(icon=icon, color=None, on_click=action).classes("qa-circle").props("round")
                        ui.label(label).classes("qa-label")

        selected_packet_id: str | None = None
        queue_worker_active = False
        watched_file_signatures: dict[str, tuple[int, int]] = {}
        active_browse = {"kind": "person"}
        participant_filters = {"query": "", "status": "all", "program": None, "has_lease": False, "date_from": None, "date_to": None}
        correction_filters = {"query": "", "caseworker": None, "program": None, "category": None, "date_from": None, "date_to": None}
        calendar_state = {"mode": "month", "anchor": date.today(), "include_documented": True}


        def metrics_values() -> list[tuple[str, int, str, str, bool]]:
            pending = len(store.pending_reviews())
            return [
                ("Needs Review", pending, "priority_high", "Issues require attention" if pending else "All clear, partner", pending > 0),
                ("Documents", len(store.data["documents"]), "description", "Preserved locally", False),
                ("Clients", len([item for item in store.data["entities"] if item["kind"] == "person"]), "groups", "On file", False),
                ("Open Packets", len(store.open_intake_packets()), "inventory_2", "In progress", False),
            ]

        def refresh_metrics() -> None:
            metrics.clear()
            with metrics:
                for label, value, icon, caption, alert in metrics_values():
                    tile_class = "stat-tile stat-tile-red" if alert else "stat-tile"
                    with ui.row().classes(f"{tile_class} flex-nowrap"):
                        with ui.element("div").classes("icon-disc"):
                            ui.icon(icon, size="28px")
                        with ui.column().classes("gap-0"):
                            with ui.row().classes("items-baseline gap-2 flex-nowrap"):
                                ui.label(str(value)).classes("stat-number" if alert else "stat-number stat-teal-number")
                                ui.label(label).classes("stat-label")
                            ui.label(caption).classes("text-xs muted")

        def selected_packet() -> dict | None:
            return next((packet for packet in store.open_intake_packets() if packet["id"] == selected_packet_id), None)

        def refresh_packets() -> None:
            nonlocal selected_packet_id
            packets = store.open_intake_packets()
            if selected_packet_id not in {packet["id"] for packet in packets}:
                selected_packet_id = packets[0]["id"] if packets else None
            packet_panel.clear()
            with packet_panel:
                with ui.row().classes("panel-bar bar-teal"):
                    ui.label("Open Packets").classes("bar-title")
                    ui.button("New packet", icon="create_new_folder", color=None, on_click=open_new_packet_dialog).classes("bar-btn").props("no-caps dense")
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
                    completeness = store.packet_completeness(packet["id"])
                    if completeness["status"] == "complete":
                        ui.label(f"{completeness['requirement']}: mapped local evidence complete").classes("text-sm text-teal-800")
                    elif completeness["status"] == "incomplete":
                        ui.label(f"{completeness['requirement']}: {len(completeness['missing'])} mapped record(s) still missing").classes("text-sm text-amber-800")
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

        def watch_intake_folder() -> None:
            """Queue stable, unseen scans from the configured local sync folder."""
            nonlocal selected_packet_id
            try:
                items = inspect_inbox(inbox_path)
            except OSError:
                return
            known_hashes = {document["sha256"] for document in store.data["documents"]}
            stable_sources = []
            visible_paths = set()
            for item in items:
                if item.path.suffix.casefold() not in SUPPORTED_INTAKE_SUFFIXES or item.sha256 in known_hashes:
                    continue
                visible_paths.add(str(item.path))
                stat = item.path.stat()
                signature = (stat.st_size, stat.st_mtime_ns)
                previous = watched_file_signatures.get(str(item.path))
                watched_file_signatures[str(item.path)] = signature
                if previous == signature:
                    stable_sources.append(item.path)
            for path in set(watched_file_signatures) - visible_paths:
                watched_file_signatures.pop(path, None)
            if not stable_sources:
                return
            packet = selected_packet()
            if not packet:
                packet = store.start_intake_packet(f"Synced intake {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                selected_packet_id = packet["id"]
            jobs = store.queue_intake_sources(packet["id"], stable_sources)
            if jobs:
                store.save()
                start_intake_worker()
                refresh_workspace()

        def refresh_intake_queue() -> None:
            queue_panel.clear()
            with queue_panel:
                counts = store.intake_job_counts()
                with ui.row().classes("panel-bar bar-teal"):
                    ui.label("Local Processing Queue").classes("bar-title")
                with ui.row().classes("w-full items-center gap-3 flex-nowrap"):
                    ui.icon("rocket_launch", size="44px").classes("text-secondary shrink-0")
                    with ui.column().classes("flex-grow min-w-0 gap-1"):
                        for label, count in [
                            ("Waiting", counts["waiting"]), ("Processing", counts["processing"]),
                            ("Completed", counts["completed"]), ("Needs Attention", counts["failed"]),
                        ]:
                            with ui.row().classes("leader-row flex-nowrap"):
                                ui.label(label)
                                ui.element("div").classes("leader-dots")
                                ui.label(str(count)).classes("font-semibold")
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
                with ui.row().classes("panel-bar bar-teal"):
                    ui.label("Detached Documents").classes("bar-title")
                packet = selected_packet()
                documents = [
                    document for document in store.data["documents"]
                    if not document.get("intake_packet_id")
                    and (document.get("staging_disposition") or {}).get("kind") != "non_viable"
                ]
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
                reviews = store.pending_reviews()
                with ui.row().classes("panel-bar bar-red"):
                    ui.label("Needs Review").classes("bar-title")
                    if reviews:
                        ui.label(f"{len(reviews)} item{'s' if len(reviews) != 1 else ''}").classes("display-label text-sm")

                if not reviews:
                    ui.label("Nothing needs review. Take five, partner.").classes("muted")
                categories = {}
                for review in reviews:
                    category = review.get("category", "other_review")
                    categories[category] = categories.get(category, 0) + 1
                if categories:
                    ui.label(" · ".join(f"{label.replace('_', ' ')}: {count}" for label, count in sorted(categories.items()))).classes("text-sm muted")
                shown = reviews if active_view["key"] == "review" else reviews[:4]
                for review in shown:
                    document = next((item for item in store.data["documents"] if item["id"] == review["document_id"]), None)
                    with ui.row().classes("w-full items-center justify-between flex-nowrap gap-3"):
                        ui.icon("picture_as_pdf", size="34px").classes("text-secondary shrink-0")
                        with ui.column().classes("gap-0 flex-grow min-w-0"):
                            ui.label(document["original_name"] if document else "Document review").classes("font-semibold text-sm")
                            ui.label(review.get("category", "other_review").replace("_", " ").title()).classes("display-label text-xs text-secondary uppercase tracking-wide")
                            ui.label(review["reason"]).classes("text-sm muted")
                        ui.button("Review", icon="fact_check", color=None, on_click=lambda review=review: open_review_dialog(review)).classes("retro-secondary shrink-0").props("no-caps dense")
                if active_view["key"] != "review" and len(reviews) > len(shown):
                    ui.label(f"View all needs review ({len(reviews)})  ›").classes("view-all").on("click", lambda: set_active_view("review"))

        def refresh_correction_findings() -> None:
            correction_panel.clear()
            with correction_panel:
                findings = filter_correction_findings(store.correction_findings(), **correction_filters)
                with ui.row().classes("panel-bar bar-teal"):
                    ui.label("Correction Findings").classes("bar-title")
                    with ui.row().classes("items-center gap-2 flex-nowrap"):
                        ui.label(f"{len(findings)} finding{'s' if len(findings) != 1 else ''}").classes("display-label text-sm")
                        ui.button(icon="filter_list", color=None, on_click=open_correction_filters).classes("bar-btn").props("round dense").tooltip("Filter correction findings")
                        ui.button("View report", icon="summarize", color=None, on_click=lambda findings=findings: open_correction_report(findings)).classes("bar-btn").props("no-caps dense")
                        ui.button("Export XLSX", icon="download", color=None, on_click=lambda findings=findings: download_correction_report(findings)).classes("bar-btn").props("no-caps dense")
                ui.label("Evidence-backed issues to resolve or include in the local correction report.").classes("text-sm muted")
                if not findings:
                    ui.label("No correction findings match the current filters." if any(correction_filters.values()) else "No active correction findings.").classes("muted")
                    return
                shown = findings if active_view["key"] == "reports" else findings[:4]
                for finding in shown:
                    with ui.card().classes("w-full shadow-none").style("background: var(--cream-bright); border: 2px solid var(--ink); border-radius: 10px;"):
                        with ui.row().classes("w-full items-start justify-between flex-nowrap gap-3"):
                            ui.icon("picture_as_pdf", size="34px").classes("text-secondary shrink-0")
                            with ui.column().classes("gap-1 flex-grow min-w-0"):
                                ui.label(f"{finding['ptc']} · {finding['category']}").classes("font-semibold text-sm")
                                if finding["document"]:
                                    ui.label(finding["document"]).classes("text-sm muted")
                                if finding.get("program") or finding.get("finding_date"):
                                    ui.label(" · ".join(part for part in [finding.get("program"), finding.get("finding_date")] if part)).classes("text-xs muted")
                                ui.label(finding["error"]).classes("text-sm")
                                ui.label(f"Recommended: {finding['recommendation']}").classes("text-sm text-primary font-medium")
                            if finding["document_id"]:
                                ui.button(icon="visibility", on_click=lambda document_id=finding["document_id"]: open_document_viewer(document_id)).props("flat dense round").tooltip("View stored source")
                if active_view["key"] != "reports" and len(findings) > len(shown):
                    ui.label(f"View all correction findings ({len(findings)})  ›").classes("view-all").on("click", lambda: set_active_view("reports"))

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

        browse_kinds = [
            ("person", "Participants", "groups"), ("landlord", "Landlords", "badge"),
            ("property", "Properties", "home"), ("unit", "Units", "meeting_room"),
            ("program", "Programs", "flag"), ("lease", "Leases", "history_edu"),
        ]
        kind_labels = {kind: label for kind, label, _ in browse_kinds}

        def refresh_relationship_search() -> None:
            relationship_panel.clear()
            with relationship_panel:
                with ui.row().classes("search-anchor w-full items-center gap-3 flex-nowrap"):
                    ui.icon("search", size="26px").classes("shrink-0")
                    query = ui.input(placeholder="Search landlords, properties, participants, files...").props("borderless clearable").classes("flex-grow min-w-0")
                    search_button = ui.button("Search", color=None).classes("retro-primary shrink-0").props("no-caps")
                query.value = global_search["query"]
                directory_counts: dict[str, int] = {}
                for row in store.entity_directory():
                    directory_counts[row["kind"]] = directory_counts.get(row["kind"], 0) + 1
                with ui.row().classes("w-full items-center gap-2 flex-wrap pl-6"):
                    ui.label("BROWSE EVERYTHING:").classes("display-label text-[10px] tracking-widest muted")
                    for kind, label, icon in browse_kinds:
                        with ui.element("div").classes("browse-chip") as chip:
                            ui.icon(icon, size="14px")
                            ui.label(f"{label} ({directory_counts.get(kind, 0)})")
                        chip.on("click", lambda kind=kind: browse_kind(kind))

                    with ui.element("div").classes("browse-chip upload-chip-teal") as upload_pill:
                        ui.icon("cloud_upload", size="14px")
                        ui.label("UPLOAD DOCS")
                    upload_pill.on("click", lambda: open_upload_dialog())

                    ui.label("Similar names are never silently merged.").classes("text-xs muted")
                results = ui.column().classes("w-full gap-2")

                def open_upload_dialog() -> None:
                    with ui.dialog() as dialog, ui.card().classes("w-[34rem] max-w-full p-5"):
                        with ui.row().classes("w-full items-center justify-between mb-2"):
                            with ui.row().classes("items-center gap-2"):
                                ui.icon("cloud_upload", size="24px").classes("text-teal-700")
                                ui.label("Upload Documents").classes("text-xl font-semibold")
                            ui.button(icon="close", on_click=dialog.close).props("flat round dense")
                        ui.label("Select multiple files or drag email attachments directly to stage into your local intake folder.").classes("text-sm muted mb-3")
                        ui.upload(
                            label="📁 Pick or Drop Files",
                            multiple=True,
                            auto_upload=True,
                            on_upload=lambda e: (handle_file_upload(e), dialog.close()),
                        ).props("flat color=teal text-color=teal-10").classes("retro-secondary w-full")
                    dialog.open()


                def browse_kind(kind: str) -> None:
                    active_browse["kind"] = kind
                    global_search["query"] = ""
                    participant_filters["query"] = ""
                    set_active_view("files")

                def show_directory(kind: str) -> None:
                    label = kind_labels[kind]
                    rows = store.entity_directory(kind)
                    ui.label(f"Every recorded {label.lower()[:-1] if label.endswith('s') else label.lower()} in this workspace: {len(rows)}").classes("text-sm font-medium")
                    if not rows:
                        ui.label(f"No {label.lower()} are recorded yet. They appear here as scanned documents establish them.").classes("text-sm muted")
                    for row in rows:
                        with ui.row().classes("w-full items-center justify-between flex-nowrap gap-3"):
                            with ui.column().classes("gap-0 min-w-0"):
                                headline = row["name"] + (f" — {row['identifier']}" if row["identifier"] else "")
                                ui.label(headline).classes("text-sm font-medium")
                                details = [f"{row['relationship_count']} recorded connection{'s' if row['relationship_count'] != 1 else ''}"]
                                if row["aliases"]:
                                    details.append("also searchable as " + ", ".join(row["aliases"]))
                                ui.label(" · ".join(details)).classes("text-xs muted")
                            if kind == "person":
                                ui.button("Open file", icon="folder_open", on_click=lambda person_id=row["entity_id"]: open_participant_file(person_id)).props("flat no-caps dense").classes("shrink-0")
                            else:
                                ui.button("Open profile", icon="hub", on_click=lambda entity_id=row["entity_id"]: open_entity_profile(entity_id)).props("flat no-caps dense").classes("shrink-0")

                def run_search() -> None:
                    global_search["query"] = (query.value or "").strip()
                    results.clear()
                    needle = global_search["query"].casefold()
                    browse_match = browse_kind_from_query(global_search["query"])
                    with results:
                        if browse_match:
                            show_directory(browse_match)
                            return
                    matches = store.universal_search(global_search["query"])
                    with results:
                        if not needle:
                            ui.label("Start with any name, place, identifier, or file name — or browse a category above.").classes("text-sm muted")
                        elif not any(matches.values()):
                            ui.label("No local records match that search.").classes("text-sm muted")
                        else:
                            if matches["entities"]:
                                ui.label("Matched records").classes("text-sm font-medium")
                            for entity in matches["entities"]:
                                with ui.row().classes("w-full items-center justify-between flex-nowrap gap-3"):
                                    with ui.column().classes("gap-0 min-w-0"):
                                        ui.label(f"{entity['name']} ({entity['kind'].replace('_', ' ')})").classes("text-sm")
                                        if entity["aliases"]:
                                            ui.label("Aliases: " + ", ".join(entity["aliases"])).classes("text-xs muted")
                                    with ui.row().classes("gap-1 shrink-0"):
                                        if entity["kind"] == "person":
                                            ui.button("Open file", icon="folder_open", on_click=lambda entity=entity: open_participant_file(entity["entity_id"])).props("flat no-caps dense")
                                        else:
                                            ui.button("Open profile", icon="hub", on_click=lambda entity=entity: open_entity_profile(entity["entity_id"])).props("flat no-caps dense")
                                        ui.button("Add alias", icon="alternate_email", on_click=lambda entity=entity: open_alias_dialog(entity)).props("flat no-caps dense")
                            if matches["related_entities"]:
                                ui.label("Connected records").classes("text-sm font-medium mt-2")
                            for entity in matches["related_entities"]:
                                with ui.row().classes("w-full items-center justify-between flex-nowrap gap-3"):
                                    ui.label(f"{entity['name']} ({entity['kind'].replace('_', ' ')}) · {entity['distance']} relationship step(s)").classes("text-sm muted min-w-0")
                                    if entity["kind"] == "person":
                                        ui.button(icon="folder_open", on_click=lambda entity=entity: open_participant_file(entity["entity_id"])).props("flat dense round").classes("shrink-0").tooltip("Open participant file")
                                    elif entity["kind"] in dict(kind_labels):
                                        ui.button(icon="hub", on_click=lambda entity=entity: open_entity_profile(entity["entity_id"])).props("flat dense round").classes("shrink-0").tooltip("Open profile")
                            if matches["participant_files"]:
                                ui.label("Participant files").classes("text-sm font-medium mt-2")
                            for match in matches["participant_files"]:
                                identifier = match["hmis_id"] or match["temporary_id"] or "No identifier yet"
                                with ui.row().classes("w-full items-center justify-between"):
                                    ui.label(f"{match['name']} — {identifier} · {match['document_count']} document(s)").classes("text-sm")
                                    ui.button("Open file", icon="folder_open", on_click=lambda person_id=match["person_id"]: open_participant_file(person_id)).props("flat no-caps")
                            if matches["documents"]:
                                ui.label("Matching documents").classes("text-sm font-medium mt-2")
                            for document in matches["documents"][:12]:
                                with ui.row().classes("w-full items-center justify-between"):
                                    ui.label(f"{document['name']} · {document['type'].replace('_', ' ')}").classes("text-sm muted")
                                    ui.button(icon="visibility", on_click=lambda document_id=document["document_id"]: open_document_viewer(document_id)).props("flat dense round").tooltip("View stored source")


                search_button.on("click", run_search)
                query.on("keydown.enter", run_search)
                if global_search["query"]:
                    run_search()


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

        def open_packet_definition_editor() -> None:
            store.initialize_logical_layouts()
            # This first editor handles the current known layout. More packet
            # types can be added as independent definitions later.
            if not store.logical_layouts:
                ui.notify("No packet definitions are available.", type="warning")
                return
            layout = store.logical_layouts[0]
            with ui.dialog() as dialog, ui.card().classes("w-[62rem] max-w-full"):
                ui.label("Packet definition").classes("text-xl font-semibold")
                ui.label("These are the logical records inside one source PDF. Adjusting this map affects future recognition and selected exports; it never changes archived sources.").classes("text-sm muted")
                title = ui.input("Packet name", value=layout["title"]).classes("w-full")
                rows: list[tuple[dict, object, object, object, object]] = []
                with ui.row().classes("w-full gap-2 items-center"):
                    ui.label("Logical document").classes("w-64 font-medium")
                    ui.label("Section").classes("w-40 font-medium")
                    ui.label("Start").classes("w-16 font-medium")
                    ui.label("End").classes("w-16 font-medium")
                for part in layout["parts"]:
                    with ui.row().classes("w-full gap-2 items-center"):
                        part_title = ui.input(value=part["title"]).classes("w-64")
                        section = ui.input(value=part["section"]).classes("w-40")
                        start = ui.number(value=part["start_page"], min=1, precision=0).classes("w-16")
                        end = ui.number(value=part["end_page"], min=1, precision=0).classes("w-16")
                        rows.append((part, part_title, section, start, end))

                def save_definition() -> None:
                    updated_parts = []
                    try:
                        for part, part_title, section, start, end in rows:
                            updated_parts.append(part | {
                                "title": (part_title.value or "").strip(),
                                "section": (section.value or "").strip(),
                                "start_page": int(start.value), "end_page": int(end.value),
                            })
                        updated_layout = layout | {"title": (title.value or "").strip(), "parts": updated_parts}
                        layouts = [updated_layout if item["layout_id"] == layout["layout_id"] else item for item in store.logical_layouts]
                        store.save_logical_layouts(layouts)
                        store.save()
                    except (TypeError, ValueError) as error:
                        ui.notify(f"Packet definition could not be saved: {error}", type="negative")
                        return
                    dialog.close()
                    ui.notify("Packet definition saved locally for future intake and export.", type="positive")
                    refresh_workspace()

                with ui.row().classes("w-full justify-end mt-3"):
                    ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                    ui.button("Save definition", icon="save", on_click=save_definition).props("no-caps")
            dialog.open()

        def refresh_form_bank() -> None:
            form_bank_panel.clear()
            with form_bank_panel:
                with ui.row().classes("panel-bar bar-teal"):
                    ui.label("Form Bank").classes("bar-title")
                    ui.button("Packet definitions", icon="rule", on_click=open_packet_definition_editor).props("outline no-caps").classes("bar-btn")
                ui.label("Reusable blank forms stay here, not in a participant file.").classes("text-sm muted")
                ui.label("Packet definitions describe the logical records inside a multi-page source, such as the TLS intake packet. They are used for selected export and future completeness rules.").classes("text-sm muted")
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

        def open_review_for_document(document_id: str) -> None:
            review = next((item for item in store.data.get("review_queue", []) if item.get("document_id") == document_id and item.get("status") == "needs_review"), None)
            if review:
                open_review_dialog(review)
            else:
                open_document_viewer(document_id)

        def refresh_participant_index() -> None:
            participant_panel.clear()
            kind = active_browse.get("kind", "person")
            with participant_panel:
                if kind == "landlord":
                    with ui.row().classes("panel-bar bar-teal"):
                        ui.label("Landlord Directory & Associated Properties").classes("bar-title")
                    ui.label("Browse all recorded landlords, their properties, housed participants, and caseworkers.").classes("text-sm muted")
                    rows = store.entity_directory("landlord")
                    q = (participant_filters.get("query") or "").strip().casefold()
                    if q:
                        rows = [r for r in rows if q in r["name"].casefold()]
                    ui.label(f"{len(rows)} landlord{'s' if len(rows) != 1 else ''} recorded").classes("text-sm muted")
                    for row in rows:
                        net = store.entity_network(row["entity_id"])
                        props = net["connected"].get("property", [])
                        people = net["connected"].get("person", [])
                        with ui.expansion(f"🏢 LANDLORD: {row['name']}", value=True).classes("w-full panel p-3 my-2"):
                            with ui.row().classes("w-full items-center justify-between mb-3 pb-2 border-b-2 border-ink/20 flex-wrap gap-2"):
                                with ui.column().classes("gap-0"):
                                    ui.label(f"🏢 {row['name']}").classes("text-lg font-bold text-teal-950 tracking-tight")
                                    ui.label(f"Landlord Entity · {len(props)} Property Owned · {len(people)} Housed Participant(s) · {row['relationship_count']} Connection(s)").classes("text-xs font-semibold text-secondary")
                                ui.button("Open Landlord Profile & Network", icon="hub", on_click=lambda eid=row["entity_id"]: open_entity_profile(eid)).props("retro-primary dense no-caps text-xs")
                            if props:
                                ui.label("ASSOCIATED PROPERTIES OWNED:").classes("font-semibold text-xs text-secondary uppercase tracking-wider mt-2 mb-1")
                                for p in props:
                                    ui.label(f" • {p['name']}").classes("text-sm font-medium ml-3 mb-1")
                            if people:
                                ui.label("HOUSED PARTICIPANT TENANTS:").classes("font-semibold text-xs text-secondary uppercase tracking-wider mt-2 mb-1")
                                for person in people:
                                    with ui.row().classes("items-center justify-between ml-3 my-1 w-full"):
                                        ui.label(f" • {person['name']} (HMIS #{person.get('identifier') or 'N/A'})").classes("text-sm font-medium")
                                        ui.button("Open file", icon="folder_open", on_click=lambda pid=person["entity_id"]: open_participant_file(pid)).props("flat dense no-caps text-xs")

                elif kind == "property":
                    with ui.row().classes("panel-bar bar-teal"):
                        ui.label("Property Directory & Tenant Occupants").classes("bar-title")
                    ui.label("Browse all recorded housing properties, unit numbers, landlords, and housed participants.").classes("text-sm muted")
                    rows = store.entity_directory("property")
                    q = (participant_filters.get("query") or "").strip().casefold()
                    if q:
                        rows = [r for r in rows if q in r["name"].casefold()]
                    ui.label(f"{len(rows)} propert{'ies' if len(rows) != 1 else 'y'} recorded").classes("text-sm muted")
                    for row in rows:
                        net = store.entity_network(row["entity_id"])
                        landlords = net["connected"].get("landlord", [])
                        people = net["connected"].get("person", [])
                        landlord_name = landlords[0]["name"] if landlords else "Landlord not recorded"
                        with ui.expansion(f"🏠 PROPERTY: {row['name']}", value=True).classes("w-full panel p-3 my-2"):
                            with ui.row().classes("w-full items-center justify-between mb-3 pb-2 border-b-2 border-ink/20 flex-wrap gap-2"):
                                with ui.column().classes("gap-0"):
                                    ui.label(f"🏠 {row['name']}").classes("text-lg font-bold text-teal-950 tracking-tight")
                                    ui.label(f"Housing Property · Owner: {landlord_name} · {len(people)} Housed Tenant(s)").classes("text-xs font-semibold text-secondary")
                                ui.button("Open Property Profile & Network", icon="hub", on_click=lambda eid=row["entity_id"]: open_entity_profile(eid)).props("retro-primary dense no-caps text-xs")
                            if people:
                                ui.label("CURRENT HOUSED PARTICIPANTS:").classes("font-semibold text-xs text-secondary uppercase tracking-wider mt-2 mb-1")
                                for person in people:
                                    with ui.row().classes("items-center justify-between ml-3 my-1 w-full"):
                                        ui.label(f" • {person['name']} (HMIS #{person.get('identifier') or 'N/A'})").classes("text-sm font-medium")
                                        ui.button("Open file", icon="folder_open", on_click=lambda pid=person["entity_id"]: open_participant_file(pid)).props("flat dense no-caps text-xs")


                elif kind in {"lease", "program", "unit"}:
                    with ui.row().classes("panel-bar bar-teal"):
                        ui.label(f"{kind_labels.get(kind, kind.title())} Directory").classes("bar-title")
                    ui.label(f"Browse all recorded {kind.lower()}s and their connections.").classes("text-sm muted")
                    rows = store.entity_directory(kind)
                    ui.label(f"{len(rows)} recorded").classes("text-sm muted")
                    for row in rows:
                        with ui.expansion(f"{kind.upper()}: {row['name']}", value=True).classes("w-full panel p-3 my-2"):
                            ui.button("Open profile", icon="hub", on_click=lambda eid=row["entity_id"]: open_entity_profile(eid)).props("flat dense no-caps")

                else: # Default: Participant Files
                    with ui.row().classes("panel-bar bar-teal"):
                        ui.label("Participant Files & Staged Records").classes("bar-title")
                        ui.button(icon="filter_list", color=None, on_click=open_participant_filters).classes("bar-btn").props("round dense").tooltip("Filter participant files")
                    ui.label("Organized by Client Participant, sectioned chronologically by Upload Date.").classes("text-sm muted")
                    rows = store.participant_index(**participant_filters)
                    ui.label(f"{len(rows)} participant file{'s' if len(rows) != 1 else ''}").classes("text-sm muted")
                    if not rows:
                        ui.label("No participant files match the current search and filters.").classes("text-sm muted")
                    for row in rows[:30]:
                        person_id = row["person_id"]
                        identifier = row["identifier"] or "No identifier yet"
                        programs = ", ".join(row["programs"]) or "No program recorded"
                        with ui.expansion(f"📁 {row['name']} — {identifier} ({row['document_count']} document{'s' if row['document_count'] != 1 else ''})", value=True).classes("w-full panel p-3 my-2"):
                            with ui.row().classes("w-full items-center justify-between mb-2 pb-2 border-b border-ink/20"):
                                ui.label(f"Programs: {programs} · {row['lease_count']} Lease(s)").classes("text-xs muted")
                                ui.button("Open complete file & ledger", icon="folder_open", on_click=lambda pid=person_id: open_participant_file(pid)).props("flat dense no-caps")

                            date_groups = store.participant_documents_grouped_by_date(person_id)
                            if not date_groups:
                                ui.label("No documents linked to this participant yet.").classes("text-sm muted ml-2")
                            else:
                                for group in date_groups:
                                    ui.label(group["date_label"]).classes("font-semibold text-xs text-secondary uppercase tracking-wider mt-3 mb-1 ml-1")
                                    with ui.element("div").classes("grid grid-cols-1 md:grid-cols-2 gap-3 w-full my-2"):
                                        for doc in group["documents"]:
                                            with ui.card().classes("w-full p-3 bg-cream-bright border-2 border-ink rounded-lg shadow-sm flex flex-col justify-between h-full"):
                                                with ui.column().classes("gap-1 w-full"):
                                                    with ui.row().classes("items-center justify-between w-full flex-wrap gap-1"):
                                                        ui.icon("description", size="18px").classes("text-teal-700 shrink-0")
                                                        ui.label(doc["original_name"]).classes("font-semibold text-xs truncate flex-grow min-w-0")
                                                    with ui.row().classes("items-center gap-1 flex-wrap my-1"):
                                                        ui.badge(doc["document_type"].replace("_", " ").title(), color="teal-8").props("dense text-xs")
                                                        pill_color = {
                                                            "active_export": "positive",
                                                            "superseded_revision": "amber-9",
                                                            "needs_review": "warning",
                                                            "true_duplicate": "grey-7"
                                                        }.get(doc["status_code"], "grey")
                                                        ui.badge(doc["status_label"], color=pill_color).props("dense text-xs")
                                                    doc_details = []
                                                    if doc.get("document_date"):
                                                        doc_details.append(f"Date: {doc['document_date']}")
                                                    if doc.get("reporting_period"):
                                                        doc_details.append(f"Period: {doc['reporting_period']}")
                                                    if doc_details:
                                                        ui.label(" · ".join(doc_details)).classes("text-xs muted")

                                                with ui.row().classes("items-center justify-end gap-1 w-full mt-2 pt-2 border-t border-ink/10"):
                                                    ui.button("👁️ View Source PDF", icon="visibility", on_click=lambda did=doc["id"]: open_document_viewer(did)).props("retro-primary dense no-caps text-xs").tooltip("Instantly view original PDF source document")
                                                    if doc["status_code"] == "needs_review":
                                                        ui.button("Approve", icon="check_circle", on_click=lambda did=doc["id"]: open_review_for_document(did)).props("retro-primary dense no-caps text-xs")
                                                        ui.button("Flag", icon="flag", on_click=lambda did=doc["id"]: open_review_for_document(did)).props("retro-secondary dense no-caps text-xs").tooltip("Flag for manual review")


        def _calendar_window() -> tuple[date, date, str]:
            anchor = calendar_state["anchor"]
            mode = calendar_state["mode"]
            if mode == "year":
                return date(anchor.year, 1, 1), date(anchor.year + 1, 1, 1), str(anchor.year)
            if mode == "month":
                start = date(anchor.year, anchor.month, 1)
                end = date(anchor.year + (anchor.month == 12), 1 if anchor.month == 12 else anchor.month + 1, 1)
                return start, end, start.strftime("%B %Y")
            if mode == "week":
                start = anchor - timedelta(days=anchor.weekday())
                return start, start + timedelta(days=7), f"Week of {start.strftime('%B')} {start.day}, {start.year}"
            return anchor, anchor + timedelta(days=1), anchor.strftime("%A, %B %-d, %Y")

        def _shift_calendar(direction: int) -> None:
            anchor = calendar_state["anchor"]
            mode = calendar_state["mode"]
            if mode == "year":
                calendar_state["anchor"] = date(anchor.year + direction, anchor.month, min(anchor.day, 28))
            elif mode == "month":
                month = anchor.month + direction
                year = anchor.year + (month - 1) // 12
                month = (month - 1) % 12 + 1
                calendar_state["anchor"] = date(year, month, 1)
            elif mode == "week":
                calendar_state["anchor"] = anchor + timedelta(days=7 * direction)
            else:
                calendar_state["anchor"] = anchor + timedelta(days=direction)
            refresh_calendar()

        def _calendar_event_card(event: dict, *, compact: bool = False) -> None:
            status = event["status"] or "upcoming"
            title = event["title"] if not compact else event["title"].split(" — ")[-1]
            card = ui.element("div").classes(f"calendar-event calendar-event-{status}")
            with card:
                ui.label(title).classes("font-medium")
                if not compact:
                    ui.label(event["detail"]).classes("text-[10px]")
            if event.get("person_id"):
                card.on("click", lambda person_id=event["person_id"]: open_participant_file(person_id))

        def export_calendar_copy() -> None:
            start, end, title = _calendar_window()
            horizon = max(date.today(), end - timedelta(days=1))
            rows = store.housing_schedule_status(as_of=date.today(), through=horizon)
            events = [event for event in schedule_calendar_events(rows, include_documented=False) if event["status"] in EXPORTABLE_STATUSES and start <= event["start"] < end]
            if not events:
                ui.notify("There are no due or upcoming schedule events in this view to export.", type="warning")
                return
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
            output = exports_dir / f"Homesteader_Schedule_Copy_{_safe_export_label(title)}_{timestamp}.ics"
            export_ics(events, output)
            ui.download(output, filename=output.name)
            ui.notify(f"Created a local calendar copy with {len(events)} event(s). Import the .ics file in Google Calendar when you choose.", type="positive")

        def _safe_export_label(value: str) -> str:
            return "".join(character if character.isalnum() else "_" for character in value).strip("_")[:48] or "Schedule"

        def refresh_calendar() -> None:
            calendar_panel.clear()
            start, end, title = _calendar_window()
            horizon = max(date.today(), date(end.year, 12, 31))
            rows = store.housing_schedule_status(as_of=date.today(), through=horizon)
            events = schedule_calendar_events(rows, include_documented=calendar_state["include_documented"])
            with calendar_panel:
                with ui.row().classes("panel-bar bar-teal"):
                    ui.label("Local schedule").classes("bar-title")
                    ui.button("Export calendar copy", icon="event_available", on_click=export_calendar_copy).props("outline no-caps").classes("bar-btn")
                ui.label("A local projection of program rules and recorded evidence. It never connects to Google Calendar or sends Homesteader data anywhere.").classes("text-sm muted")
                ui.label("Export creates a selected .ics copy only; import that file into Google Calendar manually if your organization approves it. Source documents, relationships, and the Homesteader database are never included.").classes("text-sm muted")
                with ui.row().classes("w-full items-center justify-between flex-wrap gap-2"):
                    with ui.row().classes("items-center gap-1"):
                        ui.button(icon="chevron_left", on_click=lambda: _shift_calendar(-1)).props("flat round dense")
                        ui.label(title).classes("view-heading text-xl")
                        ui.button(icon="chevron_right", on_click=lambda: _shift_calendar(1)).props("flat round dense")
                        ui.button("Today", on_click=lambda: (calendar_state.update({"anchor": date.today()}), refresh_calendar())).props("flat no-caps dense")
                    mode = ui.toggle({"year": "Year", "month": "Month", "week": "Week", "day": "Day"}, value=calendar_state["mode"]).props("dense no-caps")
                    def change_mode() -> None:
                        calendar_state["mode"] = mode.value
                        refresh_calendar()
                    mode.on("update:model-value", change_mode)
                documented = ui.checkbox("Show documented items", value=calendar_state["include_documented"])
                documented.on("update:model-value", lambda: (calendar_state.update({"include_documented": documented.value}), refresh_calendar()))
                visible = [event for event in events if event["start"] < end and event["end"] > start]
                if calendar_state["mode"] == "year":
                    with ui.row().classes("w-full gap-4 flex-wrap"):
                        for month in range(1, 13):
                            month_start = date(start.year, month, 1)
                            month_end = date(start.year + (month == 12), 1 if month == 12 else month + 1, 1)
                            month_events = [event for event in events if event["start"] < month_end and event["end"] > month_start]
                            with ui.element("div").classes("calendar-month-card w-[13rem]") as month_card:
                                ui.label(month_start.strftime("%B")).classes("view-heading text-lg")
                                ui.label(f"{len(month_events)} scheduled item{'s' if len(month_events) != 1 else ''}").classes("text-xs muted")
                                for event in month_events[:3]:
                                    _calendar_event_card(event, compact=True)
                                if len(month_events) > 3:
                                    ui.label(f"+ {len(month_events) - 3} more").classes("text-xs muted")
                            month_card.on("click", lambda month=month: (calendar_state.update({"mode": "month", "anchor": date(start.year, month, 1)}), refresh_calendar()))
                elif calendar_state["mode"] == "month":
                    with ui.element("div").classes("calendar-grid w-full"):
                        for weekday in calendar_module.day_abbr:
                            ui.label(weekday).classes("calendar-weekday")
                        first_weekday, days = calendar_module.monthrange(start.year, start.month)
                        previous_month_end = start - timedelta(days=1)
                        for offset in range(first_weekday):
                            day = previous_month_end - timedelta(days=first_weekday - offset - 1)
                            with ui.element("div").classes("calendar-day calendar-day-muted"):
                                ui.label(str(day.day)).classes("calendar-day-number")
                        for day_number in range(1, days + 1):
                            day = date(start.year, start.month, day_number)
                            day_events = [event for event in events if event["start"] <= day < event["end"]]
                            with ui.element("div").classes("calendar-day"):
                                ui.label(str(day_number)).classes("calendar-day-number")
                                for event in day_events[:3]:
                                    _calendar_event_card(event, compact=True)
                                if len(day_events) > 3:
                                    ui.label(f"+ {len(day_events) - 3} more").classes("text-xs muted")
                        total = first_weekday + days
                        for day_number in range(1, (7 - total % 7) % 7 + 1):
                            with ui.element("div").classes("calendar-day calendar-day-muted"):
                                ui.label(str(day_number)).classes("calendar-day-number")
                else:
                    days = [start + timedelta(days=offset) for offset in range((end - start).days)]
                    with ui.row().classes("w-full gap-3 flex-wrap"):
                        for day in days:
                            day_events = [event for event in events if event["start"] <= day < event["end"]]
                            with ui.column().classes("calendar-month-card flex-grow min-w-[12rem] gap-2"):
                                ui.label(day.strftime("%a, %b %-d")).classes("view-heading text-lg")
                                if not day_events:
                                    ui.label("No scheduled items").classes("text-xs muted")
                                for event in day_events:
                                    _calendar_event_card(event)
                ui.label(f"{len(visible)} schedule item{'s' if len(visible) != 1 else ''} in this view. Open any item to inspect the participant file and its preserved evidence.").classes("text-sm muted mt-2")

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
            if not document:
                ui.notify("The preserved document could not be found.", type="negative")
                return
            proposed = review.get("proposed_person_id")
            proposed_name = document.get("extracted", {}).get("participant") or ""
            suggestion = store.review_suggestion(review)
            stored_path = document.get("stored_source_path")
            source_url = f"/homesteader-source/{Path(stored_path).name}" if stored_path else None
            with ui.dialog() as dialog, ui.card().classes("w-[90rem] max-w-full p-4"):
                with ui.row().classes("w-full items-center justify-between border-b pb-2 mb-3"):
                    with ui.column().classes("gap-0 min-w-0"):
                        ui.label("Review document").classes("text-xl font-semibold")
                        ui.label(document["original_name"]).classes("text-sm muted")
                    ui.button(icon="close", on_click=dialog.close).props("flat round dense")
                with ui.row().classes("w-full h-[38rem] gap-4 flex-nowrap items-stretch"):
                    with ui.column().classes("w-2/3 h-full gap-2"):
                        ui.label("PRESERVED ORIGINAL").classes("section-kicker")
                        if source_url:
                            render_preserved_source(document, source_url, "w-full h-full")
                        else:
                            ui.label("This older record has no archived source file. The available OCR text is shown in the evidence panel.").classes("text-sm text-amber-800")
                    with ui.column().classes("w-1/3 h-full overflow-y-auto p-3 bg-cream-bright border-2 border-ink rounded-lg gap-3"):
                        ui.label("REVIEW FINDING").classes("section-kicker")
                        ui.label(review["category"].replace("_", " ").title()).classes("font-semibold text-sm text-secondary")
                        ui.label(review["reason"]).classes("text-sm")
                        ui.label("SUGGESTION").classes("section-kicker mt-2")
                        ui.label(suggestion["label"]).classes("font-semibold text-sm")
                        ui.label(suggestion["detail"]).classes("text-sm muted")
                        if review.get("revision_of_document_id"):
                            original = next((item for item in store.data["documents"] if item["id"] == review["revision_of_document_id"]), None)
                            ui.label("POSSIBLE COMPLETED REVISION").classes("section-kicker mt-2")
                            ui.label(original["original_name"] if original else "Stored original").classes("text-sm")
                            ui.label("New fields: " + ", ".join(review.get("revision_fields", []))).classes("text-xs muted")
                        ui.label("EXTRACTED METADATA").classes("section-kicker mt-2")
                        metadata = {key: value for key, value in document.get("extracted", {}).items() if value}
                        if metadata:
                            for key, value in metadata.items():
                                with ui.column().classes("gap-0 border-b border-ink/10 pb-1"):
                                    ui.label(key.replace("_", " ").title()).classes("text-xs font-semibold text-teal-800")
                                    ui.label(str(value)).classes("text-sm")
                        else:
                            ui.label("No usable metadata was extracted.").classes("text-sm muted")
                        if document.get("context_annotations"):
                            ui.label("USER CONTEXT").classes("section-kicker mt-2")
                            for annotation in document["context_annotations"]:
                                ui.label(annotation["text"]).classes("text-sm muted")
                        ui.label("OCR TEXT").classes("section-kicker mt-2")
                        ui.textarea(value=document.get("source_text", "")).props("readonly dense").classes("w-full text-xs")

                ui.separator().classes("my-3")
                note = None
                context_note = None
                if suggestion["kind"] == "non_viable":
                    ui.label("Archive as a non-viable source").classes("font-medium")
                    ui.label("This records the reason, keeps the original scan and review history, and removes it from normal filing, packet evidence, and export. You can reopen it later.").classes("text-sm muted")
                    non_viable_reason = ui.input("Reason", value="Source is blank or lacks usable completed information.").classes("w-full")
                    with ui.row().classes("w-full justify-end gap-2 mt-2"):
                        ui.button("Keep in review", on_click=dialog.close).props("flat no-caps")
                        ui.button("Archive non-viable source", icon="archive", on_click=lambda: resolve("archive_non_viable", non_viable_reason.value)).props("no-caps").classes("retro-primary")
                elif suggestion["kind"] == "form_template":
                    with ui.row().classes("w-full justify-end gap-2"):
                        ui.button("Keep in review", on_click=dialog.close).props("flat no-caps")
                        ui.button("Store in Form Bank", icon="inventory_2", on_click=lambda: resolve("catalog_form")).props("no-caps")
                else:
                    ui.label("Participant association").classes("font-medium")
                    ui.label("Search by the name on the source. Open a match to inspect its existing evidence before filing.").classes("text-sm muted")
                    search = ui.input("Participant name", value=proposed_name).classes("w-full")
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
                        with match_results:
                            for match in store.search_files(search.value or ""):
                                identifier = match["hmis_id"] or match["temporary_id"] or "No identifier yet"
                                with ui.row().classes("w-full items-center justify-between"):
                                    ui.label(f"{match['name']} — {identifier} · {match['document_count']} linked document(s)").classes("text-sm")
                                    ui.button("Use this file", on_click=lambda person_id=match["person_id"]: select_person(person_id)).props("outline no-caps dense")

                    ui.button("Search participant files", icon="search", on_click=show_matches).props("outline no-caps")
                    if proposed_name:
                        show_matches()
                    new_name = ui.input("Or create provisional client", value=proposed_name).classes("w-full")
                    context_note = ui.textarea("What is this connected to?", placeholder="Optional context for a photo, message, or otherwise ambiguous record.").classes("w-full")
                    note = ui.textarea("Decision note").classes("w-full")

                    with ui.row().classes("w-full justify-between flex-wrap gap-2"):
                        with ui.row().classes("gap-2"):
                            ui.button("Leave unassigned", on_click=lambda: resolve("leave_unassigned")).props("flat no-caps")
                            ui.button("Store in Form Bank", icon="inventory_2", on_click=lambda: resolve("catalog_form")).props("flat no-caps")
                        with ui.row().classes("gap-2"):
                            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                            if review.get("revision_of_document_id"):
                                ui.button("Confirm completed revision", icon="published_with_changes", on_click=lambda: resolve("accept_revision")).props("outline no-caps")
                            ui.button("Create and file", icon="person_add", on_click=lambda: resolve("create_person")).props("outline no-caps")
                            ui.button("File with client", icon="assignment_turned_in", on_click=lambda: resolve("assign_existing")).props("no-caps")

                def resolve(action: str, override_note: str | None = None) -> None:
                    try:
                        note_value = override_note if override_note is not None else (note.value or None if note else None)
                        context_value = (context_note.value or None) if context_note else None
                        if action == "assign_existing":
                            store.resolve_review(review["id"], action, entity_id=selected_person_id, note=note_value, context_note=context_value)
                        elif action == "create_person":
                            store.resolve_review(review["id"], action, new_person_name=new_name.value or None, note=note_value, context_note=context_value)
                        else:
                            store.resolve_review(review["id"], action, note=note_value)
                        store.save()
                    except ValueError as error:
                        ui.notify(str(error), type="negative")
                        return
                    dialog.close()
                    ui.notify("Review disposition recorded locally.", type="positive")
                    refresh_workspace()
            dialog.open()

        def open_logical_export_dialog(document_id: str) -> None:
            document = next((item for item in store.data["documents"] if item["id"] == document_id), None)
            structure = (document or {}).get("logical_document_structure")
            if not document or not structure:
                ui.notify("This source does not have a recognized logical-document map.", type="warning")
                return
            with ui.dialog() as dialog, ui.card().classes("w-[44rem] max-w-full"):
                ui.label("Prepare selected export").classes("text-xl font-semibold")
                ui.label(f"{structure['title']} · {structure['page_count']} original pages").classes("text-sm muted")
                ui.label("Choose the logical documents needed now. The archived source PDF will not be changed.").classes("text-sm")
                destination = ui.input("Local export folder", value=str(exports_dir / datetime.now().strftime("%Y-%m-%d_%H%M%S"))).classes("w-full")
                checks: list[tuple[dict, object]] = []
                current_section = None
                for part in structure["parts"]:
                    if part["section"] != current_section:
                        current_section = part["section"]
                        ui.label(current_section).classes("section-kicker mt-2")
                    checkbox = ui.checkbox(f"{part['title']} (pages {part['start_page']}–{part['end_page']})", value=False).classes("w-full")
                    checks.append((part, checkbox))

                def export_selected() -> None:
                    selected = [part["id"] for part, checkbox in checks if checkbox.value]
                    if not selected:
                        ui.notify("Choose at least one logical document to export.", type="warning")
                        return
                    try:
                        outputs = store.export_document_parts(document_id, selected, local_path(destination.value or ""))
                        store.save()
                    except (OSError, ValueError) as error:
                        ui.notify(f"Export could not be prepared: {error}", type="negative")
                        return
                    dialog.close()
                    ui.notify(f"Prepared {len(outputs)} selected document(s) locally.", type="positive")

                with ui.row().classes("w-full justify-end mt-3"):
                    ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                    ui.button("Prepare export", icon="folder_zip", on_click=export_selected).props("no-caps")
            dialog.open()

        def open_document_viewer(document_id: str) -> None:
            document = next((item for item in store.data["documents"] if item["id"] == document_id), None)
            if not document:
                ui.notify("The stored document could not be found.", type="negative")
                return
            stored_path = document.get("stored_source_path")
            source_url = f"/homesteader-source/{Path(stored_path).name}" if stored_path else None
            with ui.dialog() as dialog, ui.card().classes("w-[68rem] max-w-full p-4"):
                with ui.row().classes("w-full items-center justify-between border-b pb-2 mb-2"):
                    with ui.column().classes("gap-0"):
                        ui.label(document["original_name"]).classes("text-base font-bold text-teal-900")
                        ui.label(f"{document.get('source_format', 'PDF').upper()} · {document.get('source_size_bytes', 0):,} bytes").classes("text-xs muted")
                    with ui.row().classes("items-center gap-2"):
                        if source_url:
                            ui.link("Open in new browser tab", source_url, new_tab=True).classes("text-xs text-primary")
                        disposition = document.get("staging_disposition") or {}
                        if disposition.get("kind") == "non_viable":
                            def reopen_source() -> None:
                                try:
                                    store.reopen_non_viable_document(document_id, note="Reopened from the local document viewer.")
                                    store.save()
                                except ValueError as error:
                                    ui.notify(str(error), type="negative")
                                    return
                                dialog.close()
                                ui.notify("Source returned to the review queue. Its earlier disposition remains in history.", type="positive")
                                refresh_workspace()
                            ui.button("Reopen review", icon="restore", on_click=reopen_source).props("outline no-caps dense")
                        ui.button(icon="close", on_click=dialog.close).props("flat round dense")

                if source_url:
                    with ui.row().classes("w-full h-[600px] gap-4 flex-nowrap"):
                        with ui.column().classes("w-2/3 h-full"):
                            render_preserved_source(document, source_url, "w-full h-full shadow-inner")
                        with ui.column().classes("w-1/3 h-full overflow-y-auto p-3 bg-cream-bright border-2 border-ink rounded-lg gap-2 text-xs"):
                            ui.label("EXTRACTED EVIDENCE").classes("font-bold text-xs text-secondary uppercase tracking-wider")
                            if disposition.get("kind") == "non_viable":
                                ui.label("STAGING DISPOSITION").classes("font-bold text-xs text-secondary uppercase tracking-wider")
                                ui.label("Non-viable source").classes("text-sm font-semibold text-amber-800")
                                ui.label(disposition.get("reason", "No reason recorded.")).classes("text-sm muted")
                            extracted = document.get("extracted") or {}
                            for k, v in extracted.items():
                                if v:
                                    with ui.column().classes("gap-0 border-b border-ink/10 pb-1 w-full"):
                                        ui.label(k.replace("_", " ").title()).classes("font-semibold text-[11px] text-teal-800")
                                        ui.label(str(v)).classes("muted")
                            if document.get("context_annotations"):
                                ui.label("USER ANNOTATIONS").classes("font-bold text-xs text-secondary uppercase tracking-wider mt-2")
                                for ann in document["context_annotations"]:
                                    ui.label(ann["text"]).classes("muted")
                            ui.label("RAW OCR TEXT STREAM").classes("font-bold text-xs text-secondary uppercase tracking-wider mt-2")
                            ui.textarea(value=document.get("source_text", "")).props("readonly dense").classes("w-full text-[11px]")
                else:
                    ui.label("This record has no archived source file.").classes("text-sm text-amber-800")
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

        def open_entity_profile(entity_id: str) -> None:
            try:
                network = store.entity_network(entity_id)
            except ValueError as error:
                ui.notify(str(error), type="negative")
                return
            group_titles = {
                "person": "Tenants & participants", "landlord": "Landlords", "property": "Properties",
                "unit": "Units", "lease": "Leases", "program": "Programs", "housing_move_in": "Move-in workflows",
            }
            with ui.dialog() as dialog, ui.card().classes("w-[60rem] max-w-full"):
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0"):
                        ui.label(network["name"]).classes("text-xl font-semibold")
                        ui.label(network["kind"].replace("_", " ").upper()).classes("section-kicker")
                    ui.button(icon="close", on_click=dialog.close).props("flat round")
                if network["aliases"]:
                    ui.label("Also searchable as: " + ", ".join(network["aliases"])).classes("text-sm muted")
                recorded_facts = {key: value for key, value in network["attributes"].items() if value}
                for key, value in recorded_facts.items():
                    ui.label(f"{key.replace('_', ' ').title()}: {value}").classes("text-sm")
                ui.label("Recorded connections").classes("font-medium mt-2")
                ordered_groups = [kind for kind in ("person", "landlord", "property", "unit", "lease", "program") if network["connected"].get(kind)]
                extra_groups = [kind for kind in network["connected"] if kind not in ordered_groups and network["connected"][kind]]
                if not ordered_groups and not extra_groups:
                    ui.label("No recorded relationships yet. Connections appear as documents establish them.").classes("text-sm muted")
                with ui.row().classes("w-full gap-6 flex-wrap"):
                    for kind in [*ordered_groups, *extra_groups]:
                        with ui.column().classes("gap-1 min-w-[16rem]"):
                            ui.label(group_titles.get(kind, kind.replace("_", " ").title())).classes("font-medium text-sm")
                            for item in network["connected"][kind]:
                                with ui.row().classes("items-center gap-1 flex-nowrap"):
                                    with ui.column().classes("gap-0 min-w-0"):
                                        headline = item["name"] + (f" — {item['identifier']}" if item["identifier"] else "")
                                        ui.label(headline).classes("text-sm")
                                        ui.label(" → ".join(part.replace("_", " ") for part in item["path"])).classes("text-xs muted")
                                    if kind == "person":
                                        ui.button(icon="folder_open", on_click=lambda person_id=item["entity_id"]: open_participant_file(person_id)).props("flat dense round").tooltip("Open participant file")
                                    else:
                                        ui.button(icon="hub", on_click=lambda linked_id=item["entity_id"]: open_entity_profile(linked_id)).props("flat dense round").tooltip("Open profile")
                ui.label("Stored evidence for this record").classes("font-medium mt-3")
                if not network["documents"]:
                    ui.label("No preserved document is linked to this record or its recorded network yet.").classes("text-sm muted")
                for document in network["documents"]:
                    detail = document["type"].replace("_", " ")
                    if document.get("document_date"):
                        detail += f" · {document['document_date']}"
                    with ui.row().classes("items-center gap-1 flex-nowrap"):
                        ui.label(f"{document['name']} ({detail})").classes("text-sm min-w-0")
                        if document.get("evidence_scope") == "related":
                            via = ", ".join(document.get("via", [])[:2]) or "a connected record"
                            ui.label(f"via {via}").classes("text-xs muted")
                        else:
                            ui.label("direct evidence").classes("text-xs text-teal-800")
                        ui.button(icon="visibility", on_click=lambda document_id=document["document_id"]: open_document_viewer(document_id)).props("flat dense round").tooltip("View stored source")
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
                        state = {"documented": "Documented", "missing": "Missing", "due": "Due this month", "upcoming": "Upcoming"}.get(item["status"], item["status"].title())
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

        def refresh_activity() -> None:
            activity_panel.clear()
            with activity_panel:
                with ui.row().classes("panel-bar bar-teal"):
                    ui.label("Recent Activity").classes("bar-title")
                events = list(reversed(store.data.get("ledger_events", [])))[:4]
                if not events:
                    ui.label("No recorded activity yet.").classes("muted")
                icons = {
                    "review_opened": "schedule", "review_resolved": "task_alt", "document_ingested": "download",
                    "duplicate_detected": "content_copy", "packet_opened": "create_new_folder", "packet_closed": "task_alt",
                }
                for event in events:
                    recorded = (event.get("recorded_at") or "")[:10]
                    with ui.row().classes("w-full items-center gap-2 flex-nowrap"):
                        ui.icon(icons.get(event.get("type", ""), "history"), size="20px").classes("text-secondary shrink-0")
                        with ui.column().classes("gap-0 min-w-0"):
                            ui.label(event.get("type", "event").replace("_", " ").title()).classes("text-sm font-medium")
                            if recorded:
                                ui.label(recorded).classes("text-xs muted")

        def set_active_view(key: str) -> None:
            active_view["key"] = key
            refresh_workspace()

        def apply_active_view() -> None:
            key = active_view["key"]
            labels = {
                "overview": ("WORKSPACE", "Overview", "What needs attention, locally and right now."),
                "review": ("WORKSPACE", "Errors & Review", "Resolve uncertain records with the original evidence in view."),
                "reports": ("DATA QUALITY", "Correction Reports", "Exportable, evidence-backed correction work."),
                "files": ("RECORDS", "File Index", "Browse participant records; use universal search to navigate the whole relationship network."),
                "packets": ("INTAKE", "Packets & Intake", "Bring unsorted records into a coherent local packet."),
                "calendar": ("SCHEDULE", "Local Schedule", "Zoom through locally derived program obligations before exporting a separate calendar copy."),
                "forms": ("DATA", "Form Bank", "Reusable blank forms, kept separate from participant files."),
                "queue": ("SYSTEM", "Local Queue", "Private, on-device processing status."),
            }
            kicker, title, subtitle = labels[key]
            view_kicker.set_text(kicker)
            view_title.set_text(title)
            view_subtitle.set_text(subtitle)
            metrics.visible = key == "overview"
            review_panel.visible = key in {"overview", "review"}
            correction_panel.visible = key in {"overview", "reports"}
            right_rail.visible = key in {"overview", "queue"}
            queue_panel.visible = True
            activity_panel.visible = key == "overview"
            quick_actions_panel.visible = key == "overview"
            packet_panel.visible = key == "packets"
            detached_panel.visible = key == "packets"
            calendar_panel.visible = key == "calendar"
            form_bank_panel.visible = key == "forms"
            participant_panel.visible = key == "files"
            relationship_panel.visible = True
            for button_key, button in nav_buttons.items():
                if button_key == key:
                    button.classes(add="drawer-active")
                else:
                    button.classes(remove="drawer-active")
            for tab_key, tab in tab_elements.items():
                active_class = "tab-active-red" if tab_key == "review" else "tab-active-teal"
                if tab_key == key:
                    tab.classes(add=active_class)
                else:
                    tab.classes(remove="tab-active-red tab-active-teal")

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
            refresh_calendar()
            refresh_activity()
            apply_active_view()

        refresh_button.on_click(refresh_workspace)
        ui.timer(1.5, refresh_intake_queue)
        refresh_workspace()
        if store.intake_job_counts()["waiting"]:
            start_intake_worker()
        ui.timer(5.0, watch_intake_folder)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Homesteader workspace")
    parser.add_argument("--state", type=local_path, default=Path("data/homesteader.json"))
    parser.add_argument(
        "--inbox",
        type=local_path,
        default=Path("inbox"),
        help="Local or approved sync folder to inspect.",
    )
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    build_workspace(HomesteaderStore(args.state), args.inbox)
    port = find_available_port(args.port)
    print(f"Homesteader is available locally at http://{LOCAL_HOST}:{port} (Watching folder: {args.inbox})")
    ui.run(host=LOCAL_HOST, port=port, title="Homesteader", reload=False, show=True)


if __name__ in {"__main__", "__mp_main__"}:
    main()
