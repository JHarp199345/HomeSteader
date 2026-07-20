# Identity resolution: profiles emerge from documents

Homesteader must not require users to create a client profile before uploading the first record. Documents arrive in arbitrary order; identity records emerge gradually from the evidence they contain.

## First document

When the first document for “Jasmine Morales” arrives, Homesteader creates a **provisional identity** if no known Jasmine exists. It does not need a complete profile first.

## Later documents

As contact sheets, enrollment records, declarations, and consents arrive, the system compares evidence:

- Full name is a candidate-search key, not a unique key.
- Participant/client identifiers and date of birth are hard disambiguators when present.
- Program, contact information, emergency contacts, providers, signatures, addresses, and handwriting are supporting evidence.
- Supporting evidence can rank candidates; it cannot overcome a hard conflict such as a different date of birth.

## Outcomes

| Situation | Result |
|---|---|
| No matching name exists | Create a provisional identity automatically. |
| One matching name and exact date of birth | Propose/attach to that identity. |
| Same name but a conflicting date of birth | Create a distinct provisional identity; do not merge. |
| Multiple same-name people and no hard identifier | Review with all candidates and evidence. |
| One same-name candidate but no hard identifier | Provisional association, clearly marked as unverified until stronger evidence arrives. |

## Review resolution

Review must offer ordinary-language choices:

- “This belongs to Jasmine Morales — TLS Adult SPA 2.”
- “This is a different Jasmine Morales; create a new person.”
- “Leave unassigned for now.”

The correction becomes a ledger event and a local precedent. It never rewrites the source document or pretends that a missing identifier was present.

## Handwriting

Handwriting may be a useful supporting clue after image processing exists, especially when every other field is nearly identical. It cannot be a sole identity key: signatures may be illegible, copied, shared, or misread. A hard conflict or unresolved tie still goes to review.
