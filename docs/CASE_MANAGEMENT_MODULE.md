# Case-management module: first domain implementation

The case-management module teaches Homesteader how to interpret a narrow set of records while the generic core continues to own source preservation, duplicate handling, ledgers, provenance, review, and corrections.

## Initial entities

```text
Participant
Program
Case ledger (participant + program)
Document
```

## Initial document types

| Document | Required facts for automatic filing | Ledger event |
|---|---|---|
| Program enrollment | HMIS number, participant, and program | `program_enrollment_recorded` |
| Completed consent to share information | HMIS number, participant, and program | `consent_recorded` |
| Income declaration | HMIS number, participant, and reporting period | `income_declaration_recorded` |
| Blank consent form | No participant/program required; it belongs in the Form Bank | `form_cataloged` |

## Relationship model

```text
Participant ── enrolled_in ──> Program
Participant ── has_case ──> Case Ledger
Document ── documents ──> Case Ledger
```

The system does not create a participant/program case solely from a signature similarity, partial surname, or an AI confidence score. Missing identity context goes to review.

## Module contract

Future domain modules follow the same shape: declare document types, required hard facts, ledger event names, entity roles, and validation rules. Property operations and case management therefore share one core rather than becoming separate products.
