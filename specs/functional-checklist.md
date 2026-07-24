# Homesteader — Functional Checklist (action → expected outcome)

The systematic list of what the app does and what *should* happen. Each item gets an ID so the
Playwright suite can report pass/fail per line. **Eyeball this and correct anything wrong / add
anything missing** — you know the intended behavior; I'm inferring from the running UI + the specs.
Items marked ⚠️ are ones I'm least sure of.

Legend: ✅ = confirmed working when I looked · ⚠️ = needs your confirmation · ❓ = haven't verified yet

---

## A. App shell & render
- **A1** Load `/` → page renders; main content pane is NOT empty (search bar + File Index visible). ✅
- **A2** No server tracebacks and no browser console errors on load. ✅
- **A3** Left sidebar shows all nav items: Participant Files, Errors & Review, Dashboard, Correction Reports, Packets & Intake, Schedule, Form Bank. ✅
- **A4** Auto-Watch Folder indicator shows the watched folder (currently `inbox`). ✅

## B. Operator identity (the new feature)
- **B1** On an unconfirmed identity, the amber "Identity Confirmation Required" banner shows, naming the OS-detected name. ✅
- **B2** Operator chip shows `OPERATOR: <name>` + "Unconfirmed — click to verify". ✅
- **B3** Click "Confirm Identity Now" (or the chip) → identity dialog opens with editable name + aliases. ⚠️
- **B4** Edit name to "Jesse Harper", add alias "Jessie Harper", Save → dialog closes, chip shows Confirmed, banner disappears. ⚠️
- **B5** Identity persists across reload (stored in `operator_identity`). ⚠️

## C. Navigation (each view loads without error)
- **C1** Click Participant Files → File Index view. ✅
- **C2** Click Errors & Review → review workbench. ⚠️
- **C3** Click Dashboard → stats/overview. ❓
- **C4** Click Correction Reports → findings/report view. ❓
- **C5** Click Packets & Intake → packet view. ✅
- **C6** Click Schedule → local calendar view. ❓
- **C7** Click Form Bank → form catalog + packet-definition editor. ❓

## D. Search & browse
- **D1** Browse chips show live counts: Participants / Landlords / Properties / Units / Programs / Leases. ✅
- **D2** Type a name in universal search + Search → results filter to matching records. ⚠️
- **D3** "Similar names are never silently merged" behavior — near-duplicate names surface for review, not auto-merge. ⚠️

## E. Document upload & ingest
- **E1** "UPLOAD DOCS" → file picker; upload a PDF → it ingests into the active packet. ⚠️
- **E2** Auto-watch: a file dropped in `inbox/` is auto-ingested on the next scan. ✅
- **E3** Ingest of a doc with a participant/HMIS ID → filed to that participant's record. ⚠️
- **E4** Ingest of a doc with NO identity (e.g. a blank form) → flagged "Missing Identity" in Needs Review, not filed. ✅
- **E5** Exact-duplicate upload (same content hash) → flagged "Duplicate Check", not double-filed. ✅
- **E6** **Foreign doc** (caseworker name ≠ operator, e.g. "Dana Cortez") → moved to `set_aside/`, one ledger note, ZERO entities created. ⚠️
- **E7** **Operator alias** (submitted "Jessie Harper") → files normally, NOT set aside. ⚠️

## F. Packets & Intake
- **F1** "New packet" → creates an open packet, becomes active. ⚠️
- **F2** Active-packet combobox switches between packets. ⚠️
- **F3** "Add documents" / "Queue new scans" → adds docs to the packet. ⚠️
- **F4** "Close packet" → packet status becomes closed (and schedule auditing activates — see H). ⚠️
- **F5** Packet document row → "Inspect PDF" opens the preserved source. ✅

## G. Participant Files & records
- **G1** File Index lists participant files, grouped by client, chronological by upload date. ✅ (empty when store empty)
- **G2** A participant file shows their linked documents + relationship network (landlords/properties/units/leases). ⚠️
- **G3** Two same-named participants (e.g. two "Jasmine Morales", different HMIS IDs) stay distinct, not merged. ⚠️

## H. Needs Review / Errors & Review
- **H1** Needs Review shows queued items with counts by category (missing identity, duplicate, classification). ✅
- **H2** "Review" on an item → opens the item with the original evidence in view. ⚠️
- **H3** Resolving a review (assign identity, confirm classification) → updates the record + posts a ledger event; nothing auto-resolves. ⚠️

## I. Correction Reports / Findings
- **I1** Correction Findings tab/view lists discrepancies across the caseload. ❓
- **I2** "Export correction report" → produces an .xlsx file locally. ⚠️
- **I3** (future) discrepancy checks per the taxonomy (missing fields, amount mismatch, off-schedule dates, vendor novelty, caseworker mismatch). ❓ not built yet

## J. Schedule
- **J1** Schedule view shows a local calendar (Month/Week/Day, current period). ❓
- **J2** With an OPEN packet, schedule auditing is suppressed (0 events by design). ⚠️
- **J3** With a CLOSED packet + preserved evidence, schedule derives events (intake/quarterly/annual/recert due dates). ⚠️
- **J4** "Export calendar copy" → produces a selectable .ics file only (never syncs/sends). ⚠️

## K. Form Bank
- **K1** Form Bank view lists cataloged blank forms with thumbnails. ❓ (contested — verify)
- **K2** Upload a blank form → added to the Form Bank as a template with a thumbnail. ⚠️ (the piece I thought was removed)
- **K3** "Inspect PDF" on a form → opens the preserved blank. ✅
- **K4** Packet-definition editor → select a layout (TLS Intake / Landlord Move-In), edit its parts, Save → persists. ⚠️ (rewritten by Gemini — verify it saves)
- **K5** A recovered/recorded form shows in the Form Bank. ⚠️

## L. Ledger / audit (defensibility)
- **L1** Every filing/action posts an append-only `ledger_events` entry. ⚠️
- **L2** The app never deletes or alters a source document (read-only toward evidence). ⚠️
- **L3** (future) presence pulse writes a tombstone when a recorded source goes missing. ❓ not built yet
