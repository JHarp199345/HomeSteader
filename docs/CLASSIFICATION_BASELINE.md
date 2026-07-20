# Classification baseline: characteristics first, AI second

Homesteader should not need an AI call to make every obvious sorting decision. It begins with observable characteristics and uses AI to improve hard cases.

| Signal | Initial disposition |
|---|---|
| Exact content hash already exists | Duplicate of the stored original; do not create a second document record. |
| Blank template title plus no completed identity/signature fields | Form Bank. |
| Completed form with client/tenant/program identifiers | Candidate for a domain module's record or ledger. |
| No usable identity, context, or reliable document type | Inbox / Needs Review. |
| Strong identifiers and an explicit reference to a known prior document | Link automatically if hard matching rules agree. |

## Blank forms are a legitimate destination

An uncompleted document is not a failed classification. It is a reusable operational asset. Homesteader should catalog it in a Form Bank with title, source, version when known, printable copy, and duplicate detection.

## Duplicate stages

1. **Exact duplicate (now):** same content hash. Keep one original record and record that another identical upload was encountered.
2. **Near duplicate (now, first pass):** normalized text identifies casing, whitespace, and punctuation-only variations and sends the candidate to review. OCR cleanup and page/image fingerprints are the next improvement.
3. **Version relationship (later):** a changed document can be marked as a newer version, amended version, or related form.

AI can suggest near duplicates and relationships, but it should never delete originals automatically.
