# Security model: local core, explicit disclosure boundary

## The rule

Homesteader's document store, entity graph, ledgers, search index, and core processing run locally. The core exposes no web server, listens on no network port, and contains no outbound network client.

The default rule is simple:

> A document may enter the local core. It may not leave the local core through Homesteader.

This applies to source files, OCR text, extracted facts, embeddings, search results, relationship graphs, and ledger history unless the user deliberately routes a selected item through a configured provider.

## Important limitation

“No endpoint” protects Homesteader from being a network service. It does **not** make an internet-connected AI application trustworthy by itself. If ChatGPT, Claude, Gemini, or another cloud-connected host can read local document text, that host may transmit the text according to its own architecture and permissions.

Therefore a cloud-connected host must never receive unrestricted database access. Homesteader keeps a separate adapter boundary so it can make a user-selected disclosure visible and attributable—not prohibit approved work AI use.

## Processing modes

### Local mode — default and required for sensitive records

- Local model/runtime only (for example, a model served on the same device or private machine).
- No outbound request from Homesteader.
- Full document text can be processed locally.

### External-assistant mode — user-configured, never silent

- No direct database reads or bulk exports by a provider.
- A configured provider may process selected items, either through a future adapter or a manual handoff to an approved work AI application.
- The application should show what would leave the device, who receives it, and why; users choose their preferred level of automation.
- The core records provenance when a provider result is imported, but never grants broad file-system or database access.

This automated mode is not implemented in the prototype. Manual use of an approved AI application remains a valid workflow.

## Threats this architecture addresses

- Accidental public exposure through a web API.
- Silent upload of a document archive to an AI provider.
- A host application browsing the entire document store.
- Source records being committed to source control.
- Irreversible AI-generated metadata corrupting the record.

## Baseline safeguards now

- No network libraries or endpoints in the prototype.
- Original source text and hash are kept locally in the state file.
- Relationships carry provenance and can be corrected without changing source material.
- Local state and inbox folders are excluded from Git.
- The provider policy rejects unconfigured providers by default and can record explicitly approved provider identities without adding network behavior.

## Safeguards required before real workplace or client records

1. Obtain the employer's written authorization and follow its HMIS, privacy, retention, and incident-response policies.
2. Use a device and local storage approved for that information; enable full-disk encryption and an account lock.
3. Add authentication, authorization, encrypted backups, audit logs, and a documented deletion/retention model.
4. Determine whether each record class contains protected health information, personally identifiable information, or contractual restrictions.
5. Do not connect cloud AI, email, or web-research adapters to such records without explicit organizational approval.

Homesteader is not yet suitable for real client, tenant, health, or workplace records.
