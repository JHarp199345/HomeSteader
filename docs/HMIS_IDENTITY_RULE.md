# HMIS identity rule

For case-management records, HMIS number is the participant’s hard primary key.

- Every case document must carry an HMIS number to be filed automatically.
- The same HMIS number links records even when names vary or are common.
- A missing HMIS number goes to review; Homesteader does not guess from a name, signature, provider, or contact list.
- Names, dates of birth, contacts, and providers remain evidence for display and data-quality checks, not substitutes for the HMIS identifier.

This makes piecemeal uploads safe: the first document can create the participant record, and any later document carrying that number resolves to the same participant without requiring a packet or a pre-created profile.
