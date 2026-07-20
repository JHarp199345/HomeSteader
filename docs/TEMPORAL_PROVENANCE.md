# Temporal provenance: repeated records, recurring events, and undated sources

The same kind of document can represent different real-world events over time. A monthly or quarterly income declaration is not a duplicate merely because its wording and amount resemble the prior declaration.

## Keep four dates separate

| Date | Meaning | Source |
|---|---|---|
| Document date | Date printed, signed, or otherwise present in the original document. | Original source document. |
| Effective/reporting period | Period the document says it covers. | Original source document. |
| Received/uploaded date | When the organization or Homesteader received the item. | System event. |
| User-recorded context date | A date a user later records with an explanation and source, such as an email trail or a documented conversation. | User provenance; never presented as the original document date. |

## Non-negotiable representation rule

Homesteader must never silently insert, alter, or imply a date on an undated source document. An undated source remains **undated**.

If a user later supplies context, the system records a separate statement such as:

> User recorded that this undated declaration was received on July 20, 2026, based on an email attachment timestamp.

That preserves the original document and makes the later context auditable. It does not backdate the source.

## Content identity versus event identity

- **Content identity:** Are these files byte-for-byte or near-identical copies?
- **Event identity:** Do they document the same occurrence, or are they separate periodic submissions?

Hash matching answers only the first question. It cannot decide the second. An exact repeat upload is therefore an **intake occurrence** and a reviewable candidate, not automatic proof that the user should discard it.

## Recurring declarations

For a dated or period-specific income declaration, Homesteader creates an event in the participant’s income ledger:

```text
Jasmine Morales — Income Ledger
  January 2026 declaration: $1,200
  February 2026 declaration: $1,200
  March 2026 declaration: $1,200
```

Equal income amounts do not merge the records. The reporting period distinguishes the events.

For an undated declaration, Homesteader creates an undated candidate and asks for the smallest missing context. It does not guess the period or rewrite the original.
