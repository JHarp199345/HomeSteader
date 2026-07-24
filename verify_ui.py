#!/usr/bin/env python3
"""
UI render smoke-test — a hard "done" gate for any change that touches the app UI.

Catches the class of bug unit tests miss: the app's logic is fine and tests pass, but the
page renders BLANK (content built outside the page container, a NiceGUI slot/timer crash, etc.).

What it does: launches the app on a scratch port with output captured, loads the page with a real
browser, and FAILS if:
  - the main content pane (.q-page-container) is empty (content not rendering),
  - expected landmarks are missing (FILE INDEX, a search input),
  - the browser console logged errors,
  - the server log contains a traceback/exception.

Run before reporting done:  .venv/bin/python verify_ui.py
Exit 0 = pass, 1 = fail.
"""
from __future__ import annotations
import re, subprocess, sys, time, urllib.request, pathlib
from playwright.sync_api import sync_playwright

HOME = pathlib.Path(__file__).resolve().parent
PORT = 8799
URL = f"http://127.0.0.1:{PORT}"

def wait_up(url: str, timeout: int = 30) -> bool:
    for _ in range(timeout * 2):
        try:
            urllib.request.urlopen(url, timeout=1); return True
        except Exception:
            time.sleep(0.5)
    return False

def main() -> int:
    proc = subprocess.Popen(
        [".venv/bin/python", "-m", "homesteader.app", "--port", str(PORT)],
        cwd=str(HOME), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    failures: list[str] = []
    try:
        if not wait_up(URL):
            proc.terminate()
            print("UI SMOKE TEST: FAIL\n  ✗ server did not start on", URL)
            return 1
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception:
                browser = p.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            console_errors: list[str] = []
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: console_errors.append(str(e)))
            page.goto(URL, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)  # let NiceGUI's websocket render

            # 1. main content pane must not be empty  <-- catches the blank-page regression
            el = page.query_selector(".q-page-container")
            main_len = len(el.inner_text().strip()) if el else -1
            if main_len < 20:
                failures.append(f"main content pane (.q-page-container) is empty (text len={main_len}) "
                                "— content is not rendering into the page container")

            # 2. landmarks that must be present on the home screen
            body = page.inner_text("body")
            if "FILE INDEX" not in body:
                failures.append("missing landmark: 'FILE INDEX' not found on page")
            if not page.query_selector("input"):
                failures.append("no input/search field rendered")

            # 3. browser console errors
            if console_errors:
                failures.append(f"{len(console_errors)} browser console error(s): {console_errors[:3]}")
            browser.close()
    finally:
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=5)
        except Exception:
            out = ""
        # 4. server-side tracebacks/exceptions (ignore benign pypdf warnings)
        bad = [l for l in (out or "").splitlines()
               if re.search(r"Traceback|Exception|Error|raise ", l)
               and "Ignoring wrong pointing object" not in l]
        if bad:
            failures.append(f"server log has {len(bad)} error line(s): {bad[:3]}")

    if failures:
        print("UI SMOKE TEST: FAIL")
        for f in failures:
            print("  ✗", f)
        return 1
    print("UI SMOKE TEST: PASS — main pane rendered, landmarks present, "
          "no console errors, clean server log")
    return 0

if __name__ == "__main__":
    sys.exit(main())
