# TLS packet test matrix

The supplied TLS intake packet is a blank operational reference. It is not copied into this repository. Homesteader uses fictional fixture documents that mirror its relevant structure so the project never contains participant records.

## First supported packet slices: participant identity and Tab 3 income verification

The TLS Participant Identification / Contact Information Sheet is the primary identity-anchor form. Its HMIS field is the system’s decisive identifier; name, date of birth, providers, and emergency contacts are captured as supporting evidence and data-quality checks.

| Scenario | Fictional fixture | Expected behavior |
|---|---|---|
| First participant identification sheet | `tls_participant_identification_jasmine_a.txt` | Create one HMIS-confirmed participant file and preserve contact facts with their source. |
| Same name, different person | `tls_participant_identification_jasmine_b.txt` | Create a second participant file because the HMIS ID differs; never merge based on the shared name. |

The fixtures use the packet’s actual `HMIS ID #:` wording so extraction is tested against the source form’s field label.

The packet establishes that income verification occurs at intake and then again quarterly or annually. Therefore the system must model the documents as separate, dated events in one participant income ledger.

| Scenario | Fictional fixture | Expected behavior |
|---|---|---|
| Initial eligibility verification | `tls_income_eligibility_jasmine_initial.txt` | Establish or resolve Jasmine by HMIS ID and create an income-ledger event for the initial period. |
| Quarterly verification, same income | `tls_income_eligibility_jasmine_q2.txt` | Append a new quarterly event; do not mark it as a duplicate merely because the participant and amount match. |
| Quarterly verification, changed income | `tls_income_eligibility_jasmine_q3.txt` | Append a new quarterly event and preserve the changed value in the original source evidence. |

The current prototype recognizes the form family as `income_verification`. It requires a participant name, HMIS ID, and a stated reporting period for automatic filing. Missing HMIS ID or period stays in review.

## Next fixture groups

1. Lease and housing documents: establish links between a participant, landlord, property, unit, and dated agreement. A landlord or property search must then discover associated participant files through the relationship graph.
2. Consent and program documents: attach to the participant and the program case ledger.
3. Partial/undated contact material: create a provisional file or review item until an HMIS anchor arrives.
4. Repeated periodic forms: quarterly, annual, undated, accidental rescan, and an intentionally new submission with the same stated amount.
5. Case-management / housing-retention documents: append to a dated case ledger without relying on upload order.

## Rule being proven

```text
Participant HMIS ID H-000042
    -> one participant file
    -> one income ledger
       -> Initial enrollment - January 2026
       -> Quarterly recertification - April 2026
       -> Quarterly recertification - July 2026
```

The forms are evidence for distinct evaluation periods. They do not overwrite each other, and an equal income value does not make a later period a duplicate.

## End-to-end stress workflow

`tests/test_tls_stress_workflow.py` combines the fictional packet slices into one deliberately messy workflow: a blank form, participant identity, initial and quarterly income records, lease and move-in records, two same-name participants, a landlord notice requiring review, a context-annotated photo, and an exact duplicate upload. The test proves that automatic logic and human confirmation work together without using client data or requiring an AI provider.

## Relationship expansion: leases

A fictional lease can contain only a participant name, a landlord, premises, and a signing date. When exactly one known participant has that name, Homesteader connects the recorded entities as:

```text
Participant -> tenant under -> Lease -> governs -> Unit -> unit of -> Property
Landlord -> landlord for -> Property
```

That supports reverse search: a search for the landlord or property returns participant files linked through recorded relationships. If more than one participant file shares the lease name, the lease goes to review with the candidate files instead of choosing one.

When a user confirms the intended participant in review, Homesteader records that human decision and then appends the lease, unit, property, and landlord relationships with `human_review` provenance. It does not pretend the connection was automatic.

## Relationship expansion: other housing records

The same graph pattern applies to a move-in assistance request, rent-reasonableness form, landlord communication, housing search plan, or housing-retention plan. These records do not need to be leases. If they state a participant, landlord, property/unit, or date, Homesteader preserves and links the available facts without requiring the document to match one fixed form template.
