# Spec: Operator Identity + Foreign-Document Set-Aside

## CORE PRINCIPLE — do not violate anywhere in this feature
Homesteader **never signs, fills, alters, or deletes a document.** It only reads what is already on
a document, files it (or sets it aside), and records events. **The human is the only deleter.**
(Any mention of "stamp/fill/sign" elsewhere refers ONLY to the fake test-data generator writing on
practice PDFs — never to app behavior on real documents.)

## Part A — Operator identity (self-ID, not a login)
- On first run (or when identity is unset), **infer** the operator's name from the OS account:
  macOS full name via `id -F` or `dscl . -read /Users/$USER RealName`; fall back to the username.
- Show a **one-time confirm**: "You're signed in as `<name>` — is this how you sign paperwork?"
  with edit + save. The user can correct it (e.g. `JesseHarper` → `Jesse Harper`, or fix a
  misspelling like `Jessie` → `Jesse`).
- **Store an operator identity record**: canonical name + the OS username as a stable alias key +
  any variant spellings the user adds as **aliases** (e.g. `Jessie Harper`, `J. Harper`).
- No password, no login screen — this is a secured, single-user local machine; identity exists only
  to (1) match paperwork to the operator and (2) support future caseload reassignment. Not security.

## Part B — Foreign-document detection (on ingest)
- When a document is ingested, read the **caseworker / "Submitted By" name** off the document.
- Compare it to the operator identity (canonical + aliases) using the **existing identity-resolution
  logic**, so `Jessie` / `J. Harper` / no-space still resolve to the operator.
- **Match** (including via alias) → file the document normally.
- **No match** → it is a FOREIGN document → run the Set-Aside flow (Part C). Do **NOT** create any
  entities, relationships, or participant records from it. The relational graph must stay untouched.

## Part C — Set-Aside flow (foreign document)
1. **Move** the file into a dedicated folder `set_aside/` (user-facing label: "Not My Caseload").
   Never delete it, never modify it.
2. **Append one line** to `set_aside/_WHY_THESE_ARE_HERE.txt`:
   `<date> — <filename> — caseworker on document is "<doc name>"; operator is "<operator>" — not your caseload.`
3. Write **exactly one** lightweight ledger event `foreign_document_set_aside`
   `{date, filename, doc_caseworker_name, operator, reason}`. Do NOT create a full document record.
4. **Tell the user plainly**: "This paperwork is for `<name>`, not your caseload — I set it aside and
   didn't file it." with a **"Reveal in Finder"** action that opens `set_aside/`.

## Part D — Clearing + pulse closure
- The user clears `set_aside/` themselves in Finder, whenever they want, all at once.
- The **pulse** (presence check) detects the files are gone and records a closing/tombstone ledger
  event per removed item: `foreign_document_removed`. (If the pulse isn't built yet, detect and
  record removals at next startup/ingest as an interim.)

## Acceptance criteria
- Doc whose caseworker matches operator, incl. alias `Jessie` → **filed normally, NOT set aside.**
- Doc whose caseworker is a stranger (`Dana Cortez`, `Jim Bob`) → **moved to `set_aside/`**, one log
  line, one ledger event, and **zero** new entities/relationships.
- No document is ever modified or deleted by the app.
- Clearing `set_aside/` → pulse / next check records the removals.

## Do NOT (scope guard)
- Do not write onto, sign, or fill any PDF.
- Do not delete any file.
- Do not create entities/relationships/records from a foreign document.
- Do not add a login or password.
- Stay in scope: the ingest path + a new set-aside handler + the operator-identity store. Do not
  refactor unrelated code.

## Test material (already generated)
`Homesteader Test Documents/CLEAN_TEST_SET/CFA/`:
- Doc **#9 (Dana Cortez CFA)** = stranger → MUST be set aside.
- Doc **#4 (Jessie Harper CFA)** = operator alias → MUST be filed normally (NOT set aside).
Use these two to verify the match/mismatch behavior.
