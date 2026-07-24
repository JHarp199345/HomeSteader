#!/usr/bin/env python3
"""
Functional check suite — walks the app's actions from specs/functional-checklist.md and reports
pass/fail per check ID. Attaches to a running server (default http://127.0.0.1:8765).

Usage:  .venv/bin/python functional_check.py [URL]
Exit 0 if all pass, 1 if any fail.
"""
import sys, time
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
results = []
def check(cid, name, ok, detail=""):
    results.append((cid, name, bool(ok), detail))

with sync_playwright() as p:
    try:
        browser = p.chromium.launch()
    except Exception:
        browser = p.chromium.launch(channel="chrome")
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    console_errors = []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(str(e)))
    page.goto(URL, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)

    def pane():
        el = page.query_selector(".q-page-container") or page.query_selector(".q-page")
        return (el.inner_text().strip() if el else "")

    # A. shell & render
    check("A1", "home main pane renders (not blank)", len(pane()) > 50, f"pane_len={len(pane())}")
    check("A2", "no browser console errors on load", len(console_errors) == 0, str(console_errors[:2]))
    body = page.inner_text("body").lower()
    check("A3", "all 7 sidebar nav items present",
          all(x in body for x in ["participant files","errors & review","dashboard",
                                   "correction reports","packets & intake","schedule","form bank"]))
    # D. browse chips
    check("D1", "browse-everything chips present",
          all(x in body for x in ["participants","landlords","properties","units","programs","leases"]))

    # B. operator identity dialog opens
    try:
        page.get_by_text("Confirm Identity Now").first.click(); page.wait_for_timeout(900)
        opened = ("Operator" in page.inner_text("body")) or (page.query_selector("input") is not None
                 and "alias" in page.inner_text("body").lower())
        check("B3", "identity confirmation dialog opens", opened)
        page.keyboard.press("Escape"); page.wait_for_timeout(400)
    except Exception as e:
        check("B3", "identity confirmation dialog opens", False, str(e)[:90])

    # C. navigation — each view renders (non-empty pane, no new console error)
    for cid, nav in [("C1","Participant Files"),("C2","Errors & Review"),("C3","Dashboard"),
                     ("C4","Correction Reports"),("C5","Packets & Intake"),("C6","Schedule"),
                     ("C7","Form Bank")]:
        before = len(console_errors)
        try:
            page.get_by_text(nav, exact=True).first.click(); page.wait_for_timeout(1600)
            txt = pane(); new_err = len(console_errors) - before
            ok = len(txt) > 30 and new_err == 0
            check(cid, f"{nav} view renders", ok, "" if ok else f"pane_len={len(txt)} new_console_err={new_err}")
        except Exception as e:
            check(cid, f"{nav} view renders", False, str(e)[:90])

    # K. Form Bank specifics (we're on the Form Bank view now) — the contested area
    fb = page.inner_text("body").lower()
    check("K1", "Form Bank shows forms with thumbnails/inspect",
          ("inspect" in fb or "thumbnail" in fb) or page.query_selector("img") is not None)
    check("K2", "Form Bank upload control present",
          "upload" in fb or page.query_selector("input[type=file]") is not None)
    check("K4", "packet-definition editor present",
          "definition" in fb or "layout" in fb)
    browser.close()

# report
fails = [r for r in results if not r[2]]
print(f"\n{'='*60}\nFUNCTIONAL CHECK — {URL}")
print(f"{'='*60}")
for cid, name, ok, detail in results:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {cid:4} {name}" + (f"   <- {detail}" if (detail and not ok) else ""))
print(f"{'='*60}\n{len(results)-len(fails)}/{len(results)} passed, {len(fails)} failed")
sys.exit(1 if fails else 0)
