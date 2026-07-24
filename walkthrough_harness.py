"""
Walkthrough harness for evidence-logging a running NiceGUI app with Playwright.

WHY THIS EXISTS: Antigravity's built-in browser/computer-use tool is broken here
(Playwright driver 404) and expensive in tokens. This drives the real UI with the
Playwright already installed in .venv, deterministically, for ~zero model tokens.

USAGE (this is the ONLY part a walkthrough script needs to write):

    from walkthrough_harness import Walkthrough

    with Walkthrough("http://127.0.0.1:8765") as w:
        w.goto("/", state="empty workspace")
        w.event("Home / File Index",
                action="Loaded app root",
                observed=w.text_now(),
                after=w.shot("F_home_after"))

        w.click_text("NEEDS REVIEW")
        w.event("Needs Review tab",
                action='Clicked `NEEDS REVIEW`',
                observed=w.text_now(),
                after=w.shot("needs_review_after"))

    # -> writes walkthrough_evidence/EVIDENCE-LOG.md + screenshots

Run with the project venv:  .venv/bin/python your_walkthrough_script.py

RULES (do not break):
- Drive the UI only. Never substitute a store/API call for a click.
- Screenshot before (when context matters) and after every action.
- Record facts only. No pass/fail, no "works", no conclusions.
- Never resolve/delete/edit records unless the task explicitly says to.
"""

from __future__ import annotations
import datetime
import pathlib
from playwright.sync_api import sync_playwright


class Walkthrough:
    def __init__(self, base_url: str, out_dir: str = "walkthrough_evidence",
                 viewport=(1440, 900), settle_ms: int = 1200):
        self.base_url = base_url.rstrip("/")
        self.out = pathlib.Path(out_dir)
        self.shots = self.out / "screenshots"
        self.viewport = {"width": viewport[0], "height": viewport[1]}
        self.settle_ms = settle_ms
        self._n = 0
        self._events: list[dict] = []
        self._chrono: list[str] = []
        self._exports: list[str] = []
        self.browser_used = None

    # -- lifecycle -----------------------------------------------------------
    def __enter__(self):
        self.shots.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.launch()
            self.browser_used = "bundled chromium"
        except Exception as e:  # dead-CDN fallback: use installed Google Chrome
            print("bundled chromium failed, using system chrome:", e)
            self.browser = self._pw.chromium.launch(channel="chrome")
            self.browser_used = "system chrome (channel=chrome)"
        self.page = self.browser.new_page(viewport=self.viewport)
        return self

    def __exit__(self, *exc):
        try:
            self.finish()
        finally:
            self.browser.close()
            self._pw.stop()

    # -- navigation / interaction -------------------------------------------
    def goto(self, path: str = "/", state: str = ""):
        url = self.base_url + (path if path.startswith("/") else "/" + path)
        self.page.goto(url, wait_until="networkidle", timeout=30000)
        self.settle()
        self._chrono.append(f"goto {url}" + (f"  [state: {state}]" if state else ""))
        return self

    def settle(self, ms: int | None = None):
        """Wait for NiceGUI's websocket to re-render after a navigation/click."""
        self.page.wait_for_timeout(ms if ms is not None else self.settle_ms)

    def click_text(self, label: str, exact: bool = False):
        """Click a control by its visible label. Tries interactive roles first
        (tab/button/link/menuitem), then any element with the text."""
        candidates = [
            self.page.get_by_role("tab", name=label, exact=exact),
            self.page.get_by_role("button", name=label, exact=exact),
            self.page.get_by_role("link", name=label, exact=exact),
            self.page.get_by_role("menuitem", name=label, exact=exact),
            self.page.get_by_text(label, exact=exact),
        ]
        for loc in candidates:
            loc = loc.first
            try:
                if loc.count() == 0:
                    continue
                loc.scroll_into_view_if_needed(timeout=3000)
                loc.click(timeout=3000)
                self.settle()
                self._chrono.append(f"click text: {label}")
                return self
            except Exception:
                continue
        raise RuntimeError(f"click_text: could not find a clickable '{label}'")

    def fill(self, placeholder_or_label: str, value: str):
        self.page.get_by_placeholder(placeholder_or_label).first.fill(value)
        self._chrono.append(f"fill '{placeholder_or_label}' = {value!r}")
        return self

    def text_now(self, max_chars: int = 900) -> str:
        """Visible page text, trimmed — a supplement to the screenshot (which is
        the primary evidence). Screenshots are the source of truth."""
        raw = self.page.inner_text("body")
        t = " | ".join(s.strip() for s in raw.splitlines() if s.strip())
        return t[:max_chars]

    def shot(self, name: str, full_page: bool = True) -> str:
        """Screenshot -> returns the path to drop into an event()."""
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
        p = self.shots / f"{safe}.png"
        self.page.screenshot(path=str(p), full_page=full_page)
        return str(p)

    def note_export(self, path: str):
        self._exports.append(path)

    # -- logging -------------------------------------------------------------
    def event(self, surface: str, action: str, observed: str,
              starting_state: str = "", before: str | None = None,
              after: str | None = None, followups: str = "", notes: str = "",
              via: str = "UI"):
        self._n += 1
        self._events.append(dict(
            n=self._n, surface=surface, starting_state=starting_state,
            action=action, via=via, observed=observed,
            before=before, after=after, followups=followups, notes=notes,
        ))
        self._chrono.append(f"F{self._n:02d} {surface} :: {action}")
        return self

    def finish(self):
        today = datetime.date.today().isoformat()
        log = self.out / "EVIDENCE-LOG.md"
        L = []
        L.append(f"# Homesteader Functional Walkthrough Evidence Log — {today}")
        L.append("")
        L.append(f"**App URL:** {self.base_url}  ")
        L.append(f"**Browser:** {self.browser_used}  ")
        L.append(f"**Summary (counts only):** {len(self._events)} surfaces · "
                 f"{len(list(self.shots.glob('*.png')))} screenshots · "
                 f"{len(self._exports)} exported files")
        L.append("")
        L.append("_Evidence log only — no correctness conclusions drawn._")
        L.append("")
        L.append("## Full walkthrough")
        for e in self._events:
            L.append(f"### F{e['n']:02d} — {e['surface']}")
            if e["starting_state"]:
                L.append(f"- **Starting state:** {e['starting_state']}")
            L.append(f"- **Action:** {e['action']} — [via {e['via']}]")
            L.append(f"- **Observed result:** {e['observed']}")
            b = f"Before: {e['before']} · " if e["before"] else ""
            a = f"After: {e['after']}" if e["after"] else ""
            if b or a:
                L.append(f"- **Screenshots:** {b}{a}")
            if e["followups"]:
                L.append(f"- **Follow-up controls tested:** {e['followups']}")
            if e["notes"]:
                L.append(f"- **Notes for later diagnosis:** {e['notes']}")
            L.append("")
        L.append("## Exported files")
        L.extend(f"- {p}" for p in self._exports) or L.append("- (none)")
        L.append("")
        L.append("## Chronological action log")
        L.extend(f"{i+1}. {c}" for i, c in enumerate(self._chrono))
        L.append("")
        L.append("## Observations needing human interpretation")
        L.append("_(fill any neutral facts worth a human's eyes, each with its Fnn ref)_")
        log.write_text("\n".join(L))
        print("WROTE:", log.resolve())
