# Homesteader

Homesteader is a local-first, open-source framework for turning unsorted documents into a searchable record of entities, evidence, and chronological ledgers.

It starts with property records, but the core is deliberately domain-neutral: a later case-management module can model participants, programs, assessments, and referrals using the same intake, provenance, relationship, and review systems.

## Safety boundary

This repository currently uses **fictional fixtures only**. Do not add client, tenant, health, HMIS, or employer records here. Before Homesteader handles real workplace records, it needs approved storage, access control, retention, encryption, audit, and organizational-policy decisions. A local file is not automatically an authorized records system.

The core has no web endpoint or outbound network behavior. It is local-only by default. Users may later configure an approved AI provider or use an approved work AI application manually; Homesteader must never silently grant broad database access. See [the security model](docs/SECURITY_MODEL.md).

## Current prototype

The current working prototype is intentionally local and cautious. It supports:

- HMIS-oriented fictional intake records, including a contact sheet that can establish a client through an HMIS number.
- Open intake packets for a new client or a recurring document bundle scanned across several sessions.
- Packet-level client proposals when an identity-bearing document arrives before or after related documents.
- Detached documents that can be attached to an open packet later.
- Review decisions to file with an existing client, create a provisional client, or leave an item unassigned.
- Exact source-file hash checks that prevent a previously processed scan from being filed again.
- Plain text, PDF, and phone-image intake (HEIC, JPEG, PNG, and TIFF). PDFs with embedded text are read locally; image-only PDFs and images use local macOS Vision OCR when the required macOS components are available.
- A private local archive of each accepted source scan, so later review is grounded in the original record rather than extracted text alone. The intake copy is not moved or deleted.
- A local NiceGUI workspace for packet intake, upload, detached-document attachment, and review decisions.
- A folder intake action that processes only new `.pdf` and `.txt` files from `inbox/` into the active packet.

OCR-derived facts are never silently filed. They remain in review until a person confirms the client association and filing decision.

## Run it

Requires Python 3.11+. The local workspace dependencies are installed from `pyproject.toml`.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m homesteader.app --port 8765
```

Open `http://127.0.0.1:8765`. The workspace binds only to the local computer; it is not exposed to the network.

For a packet scanned over time from the command line:

```bash
.venv/bin/python -m homesteader.cli --state data/demo.json start-packet --label "New client intake"
.venv/bin/python -m homesteader.cli --state data/demo.json add-to-packet PACKET_ID fixtures/completed_consent_missing_participant.txt
.venv/bin/python -m homesteader.cli --state data/demo.json add-to-packet PACKET_ID fixtures/contact_information_jasmine.txt
.venv/bin/python -m homesteader.cli --state data/demo.json close-packet PACKET_ID
```

To use the folder intake action, place supported files in `inbox/`, choose the intended active packet in the local workspace, then select **Queue new scans**. Files remain in place; a raw-file hash prevents a later pass from processing the same file again.

The workspace queues new scans locally and processes them one at a time in the background. This keeps the intake screen usable while a large PDF, OCR pass, or local vision proposal is running. The compact queue panel shows waiting, processing, completed, and needs-attention counts; interrupted jobs return to waiting when the workspace restarts.

### Program rules and packet activation

TLS schedule rules are local, inspectable configuration rather than hidden logic. The included example is [program_rules.example.json](config/program_rules.example.json). To create a user-editable local copy beside the Homesteader state file, run:

```bash
.venv/bin/python -m homesteader.cli --state data/homesteader.json init-program-rules
```

Fresh intake packets may be uploaded in pieces. A schedule baseline from a document inside an **open** intake packet is not audited until the packet is closed; after closure, the relevant initial and later quarterly requirements can be tracked normally.

### Move-in workflows

Homesteader recognizes the source-derived Housing Services move-in packet: move-in assistance request, landlord acknowledgement, unit/owner certification, W-9, lease, ownership verification, habitability record, and applicable authorization or incentive records. Any recognized member with a safely associated participant can open or join the same local move-in workflow, regardless of scan order. The participant file shows the records present and the remaining core evidence expected for local review.

The included definition is [move_in_packet.example.json](config/move_in_packet.example.json). To create a user-editable local copy beside the state file, run:

```bash
.venv/bin/python -m homesteader.cli --state data/homesteader.json init-move-in-rules
```

This first version reports `in progress`, `needs review`, or `complete for local review`. It compares shared address/unit, rent, deposit, move-in-date, and lease-term values when multiple records state them; values are never silently overwritten. It does not decide eligibility, authorize payment, or claim a package is ready for HMIS or Accounting.

### iCloud Drive scan folder

Homesteader does not need an iCloud API or an internet endpoint to use a folder that iCloud Drive has already synchronized to this Mac. Create an approved folder in the Files app—for example, `Homesteader Intake`—and run the local workspace with that folder selected:

```bash
.venv/bin/python -m homesteader.app \
  --inbox "~/Library/Mobile Documents/com~apple~CloudDocs/Homesteader Intake"
```

Scan documents into that folder from the Files app. On the Mac, open the appropriate packet and select **Process new scans**. Homesteader reads the already-synced local copies only; it does not create a public service, browse iCloud, or transmit files. The scan folder path is displayed in the workspace so the active intake location is always visible.

Use this only under the organization’s approved iCloud/account policy. Standard iCloud Drive encryption and Advanced Data Protection are distinct settings; Homesteader does not assume or change either one.

## Current structure

- `homesteader/` — local prototype code
- `fixtures/` — fictional documents used to test the model
- `expected_results/` — intended outcomes of the fixtures
- `tests/` — automated checks
- `docs/` — technical and product decisions
- `PROJECT_PLAN.md` — product roadmap

## Core model

- **Entities** are durable identities: properties, units, people, leases, vendors, programs, participants, and assets.
- **Evidence** is the preserved original item plus extracted metadata.
- **Ledgers** are append-only chronological events affecting an entity or workflow.
- **Relationships** are explicit, provenance-carrying links such as `modifies`, `documents`, or `responds_to`.

This is not restricted to a fixed form catalog. A record contributes whichever supported facts it actually contains. For example, a lease can connect a participant name, landlord, property, unit, and agreement date. The relationship graph then supports reverse questions such as “Which participant files are associated with this landlord or property?” Same-name ambiguity remains in review rather than becoming an automatic association.

The same principle applies to housing documents that are not leases: move-in assistance requests, rent-reasonableness forms, landlord communications, and housing-search or retention plans can append their stated relationships to the participant record.

For ambiguous photos, screenshots, and scans, the review workflow accepts a short user context note: for example, “Water damage on the bedroom wall in Unit 1 at Harbor View, reported by Jasmine Morales today.” The note is preserved as user-provided provenance and becomes evidence linked to the selected participant file. It can be typed or entered with the Mac’s built-in dictation; the original image remains unchanged.

When a context note explicitly names an already-recorded property, unit, or landlord, Homesteader links that evidence to the known entity as user-context provenance. It does not create a new entity or guess from a vague phrase.

Blank or reusable forms belong in the **Form Bank**, not in an unknown participant file. Known blank forms can be cataloged automatically; for an unfamiliar blank form, the reviewer can deliberately select **Store in Form Bank**. The original stored scan remains available for later viewing or printing.

The engine must separate confirmed source facts, derived relationships, and unconfirmed AI hypotheses. Automated links must be explainable and reversible.

## Intake packets

An **intake packet** is a durable working set for one coherent client event, such as a new-client enrollment or a quarterly recertification. It can remain open while documents arrive one at a time or in an unreliable order.

1. Every source is preserved and evaluated independently.
2. Strong identity evidence, especially an HMIS number, can establish a client anywhere in the packet.
3. When one client is established, related unresolved documents receive that client as a proposed review choice. A proposal is not an automatic assignment.
4. A document scanned outside a packet can be deliberately attached to an open packet later.
5. A packet closes when the intake work is complete, leaving its source documents and decision history intact.

This is deliberately not a “most recent upload wins” model. Scan order is helpful context, not proof of identity.

## Implementation practices

- **Local first:** document extraction, PDF parsing, OCR, hash comparison, and the browser workspace run on the local computer. The project does not send documents to an AI service by default.
- **Raw source preservation:** original names, raw hashes, source format, source size, extraction method, and extracted text are retained as evidence.
- **Exact before fuzzy:** raw-byte hashes block repeat scans. Normalized text similarity creates a review candidate rather than deleting or merging records.
- **Hard identifiers before names:** HMIS identifiers and compatible identity facts carry more weight than a name, a signature, upload order, or a model confidence score. The same pattern is intended for CHAMP as that source system is added.
- **Human confirmation for uncertainty:** OCR-derived assignments, competing identities, missing identifiers, and possible duplicates remain visible in the review queue.
- **Append-only history:** client confirmation, packet proposals, duplicate detection, manual assignments, and filing decisions are ledger events rather than destructive edits.
- **Recurring records are chronological:** the same client and form type with a later stated date or reporting period is a new occurrence, not a replacement for the prior packet. Exact repeat source files are still skipped.
- **Narrow automation boundaries:** folder intake processes supported, unseen files only and requires an explicitly selected active packet. Background watching is intentionally not enabled yet.

See [packet intake](docs/PACKET_INTAKE.md), [identity rules](docs/HMIS_IDENTITY_RULE.md), [temporal provenance](docs/TEMPORAL_PROVENANCE.md), and [the security model](docs/SECURITY_MODEL.md) for the underlying decisions.

## Sorting before AI

AI is an enhancement, not a prerequisite. The first sorting pass uses observable characteristics: document wording, completed identity fields, signatures, dates, repeated records, and content hashes. An unfilled consent form belongs in a reusable **Form Bank**, not an unknown client file. Exact duplicate uploads are detected using a content hash and retained as a single original record with a duplicate event.

Near duplicates—such as a rescan with different whitespace or punctuation—are held as review candidates rather than silently discarded. See [the batch inference model](docs/BATCH_INFERENCE_MODEL.md) for how local pre-processing and a frontier model work together on a selected backlog.

Recurring records are tracked as time-based ledger events, not merged merely because their content or amounts resemble a previous submission. Undated sources remain explicitly undated; see [temporal provenance](docs/TEMPORAL_PROVENANCE.md).

The fictional TLS packet scenarios in [the TLS test matrix](docs/TLS_PACKET_TEST_MATRIX.md) cover the actual initial, quarterly, and annual income-verification structure without placing any participant data in the repository.

The project’s end-to-end fictional TLS stress workflow deliberately mixes blank forms, periodic records, same-name participants, leases, landlord records, a context-annotated photo, and duplicate intake. This validates deterministic safeguards before optional AI classification is introduced.

Optional AI integration now has a local, model-neutral proposal contract: an AI host may return document classification and source-quoted facts, while Homesteader validates that each quotation actually exists in the selected source and queues the result for human review. It never gives the host direct database write access. See [the AI proposal contract](docs/AI_PROPOSAL_CONTRACT.md).

## Correction reports

Homesteader can audit its own local record state and produce evidence-backed correction findings for the same kinds of work that a manual data-quality review catches: unresolved identity conflicts, missing HMIS confirmation, duplicate checks, OCR confirmation, missing time context, classification decisions, and missing local source archives. Each finding names the PTC when determinable, the affected document, the observed error, a clear recommended correction, and the source of the finding. It does not invent compliance violations or modify records during the audit.

The local workspace now includes a **Correction findings** panel with filters for PTC/HMIS ID, caseworker, program, error type, and finding date. **View report** shows the complete evidence-backed findings; **Export XLSX** exports exactly the currently filtered rows to a readable workbook with an `Audit Data` sheet, ready for Excel or Google Sheets. It uses only local audit findings and does not contact HMIS, CHAMP, or another external system.

For the current local prototype, generate the findings JSON and then the workbook:

```bash
.venv/bin/python -m homesteader.cli --state data/homesteader.json correction-findings > /tmp/homesteader-findings.json
node tools/export_correction_report.mjs /tmp/homesteader-findings.json correction-report.xlsx
```

The command-line export remains available for automation or troubleshooting.

## Housing Services schedules

Housing Services is now the first active domain module. A recorded TLS enrollment starts a **standard 24-month timeline**. The current local TLS schedule includes monthly CFA requests due in the first ten days, quarterly income eligibility/verification in March, June, September, and December, and annual recertification in the enrollment month. It can report whether each expected record is documented, upcoming, due, or missing and includes missing periods in the local correction report.

For an existing caseload brought into Homesteader mid-program, a quarterly checkpoint can establish the participant/program network and carry a stated enrollment date without triggering a retroactive missing-document list. Its ingestion creates a **historical baseline**; only scheduled obligations after that baseline are audited. This lets the system begin with the paperwork actually available today rather than demanding a complete historical import.

A recognized program-exit document with an exact HMIS identity, exit date, and one unambiguous program case closes future schedule expectations while retaining the complete digital record. It does not delete or hide the participant file. If a purported exit record lacks an exit date or cannot identify one program case, it goes to review rather than closing anything.

## Canonical entities and reverse lookup

Homesteader keeps properties, legal landlords, managers, units, and people as
separate canonical entities. It can record a human-confirmed alternate name
such as `Harbor View Apts.` for `Harbor View Apartments`, making either name a
reliable reverse-search entry point. It does not fuzzy-merge `Harbor View
Apartments` with `Harbor View LLC`; if they are related, that is recorded as an
explicit relationship such as `landlord_for`.

This is deliberately a configurable policy layer, not an attempt to guess every program rule. Additional TLS, ABH, shelter, and tiny-home requirements should be added only after their actual checklist, cadence, and exception policy are confirmed. Extensions, transfers, pauses, and exits must be explicit ledger events; Homesteader never assumes them.

Due-diligence forms are **event-triggered evidence**, not scheduled requirements. They document a caseworker's good-faith effort to obtain information or make contact, so their absence is never reported as a missing periodic form.

### Completed copies are not automatically duplicates

When a later upload is the same form for the same HMIS number and stated
reporting period/date, but it fills fields that were blank in an earlier copy,
Homesteader proposes a **completed revision**. It does not replace either file.
After a human confirms it, the newer source receives an append-only
`supersedes_for_fields` link to the incomplete source, recording exactly which
facts it now supports. Conflicting values, different reporting periods, and
exact re-scans still use the normal review/duplicate safeguards.

To inspect the derived schedule locally:

```bash
.venv/bin/python -m homesteader.cli --state data/homesteader.json housing-schedule
```

### Local calendar copy

The **Schedule** view projects the locally derived obligations into a year,
month, week, or day view. It is not a Google Calendar connection. **Export
calendar copy** writes only the selected due/upcoming events to an importable
`.ics` file; it does not include source documents, relationship data, or a
database connection. An authorized user can manually import that copy into a
permitted Google Calendar. Homesteader never signs in to Google, calls a
calendar API, or exposes an internet endpoint for this feature.
