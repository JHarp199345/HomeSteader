# Homesteader

## Product thesis

Homesteader is an open-source, local-first document intelligence and operations engine. It accepts unsorted records, understands what they are, connects them to the people and things they concern, and preserves a usable history without requiring the user to become a meticulous file clerk.

Property management is the first domain module. The longer-term core is reusable for other paperwork-heavy domains, including case management.

> Capture first. Clarify only when necessary.

## The problem

Traditional systems make people classify information before the computer can use it: select a folder, property, unit, tenant, document type, date, and tags. This creates friction, delayed filing, missing records, and unusable history.

Homesteader reverses that burden. The user drops an item into an inbox, scans it, forwards it, or captures it inside an active workflow. The system proposes the filing, relationships, name, and next context using evidence from the record and the existing database.

## Product principles

- Local-first and open source: the core works on a user-controlled machine or private server and does not require a Homesteader API key.
- Model-independent: users may select a local model or a supported cloud provider.
- Relationships over folders: files are evidence connected to real entities and events; folders are generated views when useful.
- Ledgers over overwritten state: changes are recorded chronologically and reversibly rather than silently replacing prior history.
- Automate the obvious: use confidence thresholds to handle clear cases without asking the user to approve every action.
- Preserve uncertainty: record whether metadata is user-provided, extracted from source material, derived, or merely an AI hypothesis.
- Human authority for consequential decisions: the system organizes, retrieves, drafts, coordinates, and summarizes; users retain legal, financial, and interpersonal judgment.
- Designed for imperfect habits: tolerate bad filenames, delayed uploads, duplicates, incomplete context, screenshots, and inconsistent naming.

## Initial domain: Housing Services operations

Homesteader's first active domain is Housing Services: participant records,
program enrollment, housing relationships, documentation obligations, and the
caseworker evidence needed to support a client. Property operations remains a
compatible future module, not the defining first use case.

### Standard schedules and event-triggered evidence

Each program module may define a verified standard duration, enrollment anchor,
and periodic requirements. TLS begins with a 24-month standard timeline and
the documented income eligibility/verification cadence. The framework derives
missing, documented, and upcoming requirements from the enrollment ledger;
extensions, transfers, pauses, and exits must be human-recorded events before
they change that timeline.

For established caseloads entering Homesteader mid-program, a periodic
checkpoint may create a historical baseline. It can prove a participant's
program relationship and record an enrollment date without causing the system
to report every unimported historical form as missing. Schedule audits begin
after that baseline.

Due-diligence forms are event-triggered evidence of a caseworker's effort to
obtain a document, make contact, or address a situation. They are never a
missing scheduled requirement.

## Compatible future domain: property operations

Homesteader helps self-managing landlords and small property teams organize and coordinate their property records. It is not bookkeeping, rent processing, tax software, tenant screening, autonomous legal advice, or an autonomous property manager.

Initial records include leases, addenda, tenant/vendor messages, maintenance records, photos, quotes, invoices, warranties, inspection records, and voice notes.

Initial operational value:

- Find every record related to a property, unit, tenant, lease, repair, vendor, or appliance.
- Connect an addendum to the lease it modifies.
- Build a coherent maintenance history from messages, photos, outreach, quotes, work, and completion evidence.
- Detect repeated repairs and unresolved recurring problems.
- Prepare vendor outreach and normalize replies, quotes, and relevant reputation information for human selection.
- Retrieve relevant contract, warranty, HOA, or insurance language with source citations; do not make legal determinations.

## Information architecture

### Entity layer

Entities are relatively stable things the system knows about.

```text
Portfolio → Property → Unit
Person (tenant, owner, vendor contact)
Lease and addendum
Vendor
Appliance / asset
Warranty / insurance / HOA policy
Document / message / photo / voice note
```

### Ledger layer

A ledger is an append-only, chronological record of events affecting a particular entity or workflow. It is analogous to an accounting ledger in structure: an originating event is followed by related events, each retaining its place in the history.

Examples:

```text
Lease ledger: signed → pet addendum → rent amendment → renewal
Maintenance ledger: report → evidence photo → outreach → quote → work → invoice → confirmation
Appliance ledger: installed → warranty → repair → repeat repair → replacement
```

Corrections are recorded as new, reversible events—not destructive overwrites. Current views are derived from the record of events.

### Completed revisions and duplicate protection

An intentionally re-uploaded completed copy of the same form is not treated as
a disposable duplicate. A completed-revision proposal requires a shared hard
identity, form type, and reporting period or document date, plus additional
fields that were absent from the earlier source and no conflicting substantive
facts. Human confirmation creates an append-only `supersedes_for_fields`
relationship; both source documents remain available. Exact raw-file matches,
recurring documents from different periods, and substantive conflicts retain
their separate duplicate/review paths.

### Evidence and relationships

Every item retains the original file plus metadata. Documents can connect to multiple entities and ledgers through explicit relationship types, such as:

`modifies`, `responds to`, `documents`, `supports`, `created for`, `confirms`, `completes`, `supersedes`, and `disputes`.

For example, a plumbing quote may respond to a vendor request, which was created for a kitchen-leak maintenance ledger, which concerns Unit 1B and its active tenant.

## Capture and automatic filing

### Universal inbox

Unsorted PDFs, images, messages, email attachments, voice notes, and other records enter one inbox. The system:

1. Preserves the original item and its source details.
2. Extracts text, names, addresses, dates, references, document type, and relevant facts.
3. Searches for matching entities and ledgers.
4. Proposes a standardized name, links, and relationships.
5. Indexes the content for direct and semantic search.
6. Creates tasks or flags relevant obligations only when supported by the source.

### Contextual capture

Ambiguous material—especially photos, screenshots, isolated messages, and voice notes—can inherit context when captured from a specific ledger or unit.

For universal-inbox uploads with insufficient context, the interface asks the smallest useful question, or accepts a one-sentence typed or spoken note:

> “This is the water stain Elena reported in Unit 1B today.”

That becomes explicit provenance, from which the system can connect the item without forcing dropdown-based filing.

## Confidence, provenance, and safe correction

### Confidence policy

| Confidence | System behavior |
|---|---|
| Very high | File and link automatically. |
| High | File automatically and surface an Undo action. |
| Medium | Present the most likely matches and ask for a quick choice. |
| Low or conflicting | Keep in Needs Review; never silently guess. |

### Metadata provenance

Each fact and relationship records its origin:

- **Confirmed fact:** explicitly stated by the user or source document.
- **Derived relationship:** strongly inferred from confirmed records (for example, the current tenant of a known unit).
- **AI hypothesis:** a tentative interpretation that must not be presented as fact.

Every automated relationship includes model/provider, confidence, evidence, timestamp, and correction history. The original document is immutable; generated metadata can be detached, relinked, merged, split, or reverted.

## AI-provider adapters

The Homesteader core sends structured tasks to an adapter and requires structured, evidence-based results. It must work with local and optional cloud models rather than requiring a particular provider.

Target adapter types:

- Ollama and OpenAI-compatible local endpoints
- LM Studio
- Local model runners such as Qwen-family models where capable
- Optional adapters for cloud AI providers when the user supplies credentials and permissions

Cloud integrations may enable email, calendar, Slack, notifications, research, or drafting where the host environment supports them. The README must clearly distinguish local processing from information sent to an external provider.

Example request responsibilities:

```text
classify document → extract entities → find candidates → propose relationships
→ return confidence, evidence, contradictions, and uncertainties
```

The deterministic application layer, not the model alone, validates constraints and records the result.

## Property-management workflows

### Lease changes

An original lease establishes tenant, property, unit, dates, terms, and parties. A later addendum is classified, matched to the correct lease, connected with `modifies`, and made jointly searchable. The system explains why the match was made.

### Maintenance

Each issue receives its own maintenance ledger. Messages, photos, vendor outreach, availability replies, quotes, work orders, invoices, and confirmation evidence attach to that ledger while also retaining links to the property, unit, tenant, vendor, appliance, and warranty where applicable.

### Vendor coordination

After user approval, Homesteader can prepare or send a shared availability request to selected vendors, collect and normalize responses, compare quote scope rather than just price, and summarize available reputation and prior-outcome information. The landlord selects and negotiates with vendors.

## Prototype: prove automatic linking

The first prototype deliberately avoids real or confidential records.

### Dummy document 1 — original lease

Create a fictional residential lease containing a landlord, tenant, property address, unit, signing date, lease dates, rent, pet restriction, appliance list, and signatures.

### Dummy document 2 — related addendum

Create a visibly different fictional pet authorization addendum that names the same tenant and premises and explicitly references the original lease date.

### Success criteria

After independent ingestion, the system must:

1. Classify the first document as a lease and create the appropriate entities.
2. Classify the second document as an addendum.
3. Match its tenant, property, unit, and referenced original lease.
4. Add an explicit `modifies` relationship to the original lease.
5. Preserve both originals and make them jointly searchable.
6. Return confidence and clear source-grounded reasons for the match.

### Dummy document 3 — ambiguity test

Create an intentionally unclear document: missing unit number, vague agreement reference, or competing candidates. The system must route it to review rather than contaminate the data with a confident-looking but unsupported link.

## Development roadmap

### Phase 0 — Foundation and prototype fixtures

- Define core data schema: entities, ledgers, events, evidence, relationships, provenance, constraints, and corrections.
- Write the three dummy documents and expected machine-readable outputs.
- Define the adapter interface and structured response schema.

### Phase 1 — Local intake and relationship proof

- Implement local file intake, text extraction, original-file preservation, hashing, and basic indexing.
- Implement lease/addendum classification, entity extraction, candidate matching, confidence thresholds, and explanations.
- Build a minimal review queue and undo/relink operations.
- Verify the three dummy-document scenarios end to end.

### Phase 2 — Searchable ledgers

- Create entity views and lease/maintenance ledger views.
- Add name-first participant-file search: show temporary and HMIS-confirmed files by name, open their evidence summaries, then let the human attach an ambiguous document or create a new provisional file. Users should never need to remember a temporary identifier.
- Support direct search and source-cited conversational retrieval.
- Generate standardized names and dynamic folder-like views without requiring folders as the primary model.
- Add a local correction-report audit: translate unresolved review items, temporary identities, source-archive gaps, and other evidence-backed data-quality problems into per-caseworker/PTC findings with a plain-language correction recommendation.
- Export correction reports as a readable Excel/Google Sheets-compatible workbook plus a machine-readable audit-data sheet. The audit must never alter source records or invent external-system discrepancies.

### Phase 3 — Context capture and maintenance workflow

- Capture photos, voice notes, and messages from inside an existing workflow.
- Add natural-language annotation for inbox items.
- Build a maintenance-ledger workflow and recurrence detection from historical events.

### Housing Services capability — handwritten records

- Keep deterministic extraction as the first pass; use a selected local
  vision-capable model only when a scanned or handwritten form needs a
  transcription or labeled-fact proposal.
- Restrict the staging client to a local loopback model endpoint and preserve
  the original scan. A visual proposal may describe what it read, but cannot
  automatically change identity, eligibility, timelines, or relationships.
- Compare models on the same fictional scans for legibility, evidence quality,
  uncertainty reporting, and unsupported-fact rate before using one with
  approved workplace records.

### Phase 4 — Provider and connector expansion

- Harden local-model support.
- Add optional cloud/provider adapters with transparent permissions.
- Add user-approved email, calendar, notification, and vendor-outreach connectors.

### Phase 5 — Sync, security, and extensibility

- Evaluate single-device, private-network, encrypted self-hosted, and optional managed sync.
- Add backup/export, audit history, access control, and documentation.
- Define a domain-module contract for case management and other future modules.

## Explicit non-goals for the first release

- General ledger accounting, bank reconciliation, taxes, rent collection, or payment processing.
- Tenant screening or automated tenant decisions.
- Autonomous legal interpretation, legal notices, spending, or vendor negotiation.
- Rebuilding a full enterprise property-management platform.
- A giant generic multi-industry product before the property workflow is proven.

## Open questions

1. What database and local search stack best supports append-only ledgers, relationship queries, attachments, and correction history?
2. Which local models and document-processing pipeline meet the prototype’s accuracy and hardware requirements?
3. What hard constraints should reject a proposed match (ended lease, incompatible dates, different unit, conflicting legal name, etc.)?
4. How should duplicate files, corrected documents, and successive versions be represented?
5. What is the smallest interface that makes review and correction effortless?
6. Which user-authorized research and review sources are reliable and permissible to integrate?
7. What sync architecture preserves privacy while remaining easy for nontechnical users?
8. What module contract lets property operations and later case management share the core without becoming one vague product?

## Initial definition of done

The first milestone is complete when a nontechnical user can upload two fictional but related documents in any order and Homesteader correctly files, names, links, explains, and retrieves them—with no folder selection or manual tagging—and safely requests help when the evidence is ambiguous.

## Identity reconciliation

Case records use HMIS number as the permanent participant identifier. When incomplete documents arrive first, Homesteader may create a temporary file identifier. A unified search shows temporary and confirmed files together. After human verification, confirming an HMIS number replaces the temporary identifier while preserving the file’s documents, relationships, and ledger history.

### Name-first reconciliation search

Identifiers are system references, not user memory requirements. When an uploaded document cannot be associated automatically, the user searches the participant name visible on that document. Homesteader returns every relevant confirmed or temporary file associated with that name, including a concise document and relationship summary. Opening a result presents its documents in a scrollable viewer for verification. The user can attach the new document to that file, return to the results, or create a new file if no result is correct. IDs may be displayed for clarity but are never required as search input.
