# Corrections & Discrepancy Taxonomy — inferred starter

Goal: automate what a caseworker currently does by eye + Excel — compare values across a
participant's assembled file against shared reference "instruments," and flag what doesn't
reconcile, with enough evidence to defend or correct it. Feeds the existing `correction_findings`
feature. **Never auto-fixes** — it produces a reviewable finding; corrections happen by the
reverse-entry / re-upload flow (consistent with "the app never alters documents").

## Shape of every finding
`[category] · what's wrong · evidence (doc(s) + value(s) compared) · reference violated · severity · suggested correction`

## Reference instruments the checks depend on (build/verify these or the checks can't run)
- **Scheduler** — when quarterlies / recerts / reviews are *due* (temporal checks need this).
- **Assembled participant file** — the cross-document view (consistency checks need this).
- **Form Bank** — the definition of each form and what a *complete* one contains (its fields, which
  are required, and each field's expected role). Completeness reads THIS, not a hand-built map.
- **Registries** — vendors, approved program-name index, operator/caseworker identity, participants.
- **Evidence links** — every recorded value points back to its source document.

---

## A. Completeness & correct placement — measured against the Form Bank definition
The **Form Bank already defines each form and what a complete one looks like** (fields, which are
required, each field's expected role). These checks read that definition instead of a hand-built map.
Three layers: is the form there → are its fields filled → are they filled with the *right kind of
value in the right slot*.
- **A1 Missing required document** — an expected form (per scenario/schedule) is absent from the file (e.g. CFA ≥ $600 needs a W-9; a move-in needs lease + landlord ack + unit cert).
- **A2 Required field empty** — a field the Form Bank marks required is blank (name, HMIS ID, date, amount, program, GL code, signature).
- **A3 Missing signature / approval** — form unsigned, or the approver chain is incomplete (caseworker/PM/director).
- **A4 Missing supporting evidence** — a declared value (esp. income) has no backing document (pay stub / bank statement / budget tool).
- **A5 Field-role mismatch** — the value doesn't fit the field's role: the *caseworker* field must resolve to the operator / a caseworker; the *participant (PTC)* field to a participant; a date field to a date; an amount field to a number. Flag right-kind-wrong-entity (a participant's name sitting in the caseworker slot) or a value that resolves to no known entity.
- **A6 Omitted / placeholder / invalid name** — a required name left blank, or filled with initials / a nickname / placeholder / garbage that doesn't resolve to a real name. Reliable catches: empty, no registry/identity match, wrong format, known placeholder text. Genuinely novel garbage → low-confidence "flag for a human" (E3), never a silent pass.
- **A7 Swapped fields** — correct values in the wrong slots (caseworker ↔ participant transposed).

## B. Consistency — values that should match, don't (cross-document reconciliation)
- **B1 Amount mismatch** — the same figure differs across docs (budget tool vs CFA amount vs lease rent vs deposit). Identify: compare numeric fields that should be equal, beyond a tolerance.
- **B2 Income mismatch** — self-declared income ≠ income evidenced by pay stubs / bank statements. Identify: declared value vs computed-from-evidence, flag over tolerance.
- **B3 Identity mismatch** — participant name / HMIS ID differs across docs in one file (typo or wrong participant). Uses identity resolution.
- **B4 Program mismatch** — program named differs across the file, or isn't in the approved program-name index.
- **B5 Vendor/landlord mismatch** — vendor name/address inconsistent across the move-in packet.

## C. Temporal / schedule — dates wrong or off-cadence (needs the scheduler)
- **C1 Illogical date order** — move-in before lease-signed; recert before enrollment; exit before entry; deposit after move-in with no explanation.
- **C2 Off-schedule document** — a "quarterly" dated outside its expected window per the scheduler's cadence. Identify: doc date vs scheduled due window.
- **C3 Missing scheduled document** — a quarterly/recert is due (per schedule) but absent from the file.
- **C4 Overdue / expired** — enrolled > 1 year with no recert; certification lapsed.
- **C5 Duplicate for a period** — two quarterlies covering the same quarter.

## D. Rule / validity — a business rule is violated
- **D1 Vendor novelty error** — "New Vendor" checked but vendor already in registry (or "Established" with no prior record).
- **D2 Caseworker/operator mismatch** — doc's caseworker ≠ operator (foreign document; set-aside flow).
- **D3 Bad checkbox state** — New *and* Established both checked, or neither; missing GL code; conflicting selections.
- **D4 Threshold rule** — amount over a limit without the required doc/approval (e.g. ≥ $600 → W-9; large amount → extra approver).
- **D5 Eligibility rule** — program requires fields/conditions that aren't met.

## E. Data quality — malformed or impossible values
- **E1 Malformed value** — a "date" that isn't a valid date; an "amount" that isn't numeric; HMIS ID not matching the expected format.
- **E2 Impossible value** — negative amount; DOB in the future; date outside a sane range.
- **E3 Low extraction confidence** — an OCR/extracted field the system is unsure it read correctly → flag for a human's eyes.

## F. Provenance — evidence / defensibility gaps
- **F1 Unsourced value** — a recorded fact not backed by any uploaded document.
- **F2 Unaffiliated document** — a doc that couldn't be tied to a participant (or is a foreign doc).
- **F3 Silent change** — a value differs from a prior recorded value with no correcting document (should have gone through reverse-entry).

---

## Classification scheme (for the report)
- **Category:** A–F above.
- **Severity / action:** `Blocker` (can't file until fixed) · `Correction-needed` (file, but flag for correction) · `Note` (informational).
- Each finding carries a **suggested correction** and **which document to re-upload** to clear it.

## Notes
- Many checks share the same primitives: *field presence*, *value equality within tolerance*,
  *date vs schedule*, *lookup against a registry*, *value → evidence link*. Build those primitives
  once; each discrepancy type is a small rule composed from them. (This is the "precise instruments
  in coordination" idea — a handful of measuring tools, reused.)
- This list is inferred from the current forms + our discussions; it is meant to be *extended* by the
  coworker's real checklist, not to replace it. Structure it as `type → how to identify → docs
  compared → classification → correction` so his items drop straight in.
