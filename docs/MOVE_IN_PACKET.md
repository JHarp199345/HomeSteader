# Housing move-in packet

This is Homesteader's first source-derived Housing Services workflow. It is an
editable relationship definition, not an eligibility decision, payment
authorization, or external-system submission rule.

The related local template is
[`move_in_packet.example.json`](../config/move_in_packet.example.json). It was
derived from the supplied blank landlord packet and deliberately contains no
participant, landlord, property, tax, or payment data.

## Packet members

| Record | Role | Expected status |
| --- | --- | --- |
| Move-In Assistance Request Form | Opens or supports the move-in workflow | Core |
| Landlord Rental Assistance Acknowledgement | Direct-rental-assistance agreement | Core |
| Unit Information and Owner Certifications | Unit, owner/payee, rent, and property certification | Core |
| Form W-9 | Tax identity for the person or business receiving payment | Core |
| Signed lease / rental agreement | Tenancy evidence | Core |
| Property ownership verification | External evidence from the assessor's office | Core |
| Habitability Standards for Permanent Housing | Property approval evidence | Core |
| Letter of Authorization | Proof a representative may sign landlord forms | Conditional |
| Landlord Incentive Fee Agreement | Incentive-payment evidence | Conditional |

The supplied PDF packages the W-9 across six pages, but Homesteader treats it
as one logical record. The habitability checklist and certification page are
also one logical record.

## Relationship model

```text
Participant -- signs / occupies --> Lease -- covers --> Unit -- located at --> Property
                                      |                         |
                                      |                         +-- verified by --> Ownership verification
                                      |                         +-- approved by --> Habitability record
                                      |
                                      +-- managed by --> Property manager

Legal owner -- owns --> Property
Payee -- receives payment for --> Move-in workflow
W-9 -- identifies tax entity for --> Payee
Authorized representative -- may sign for --> Legal owner or agent
```

Legal owner, payee, property manager, and authorized signer are deliberately
separate entities. A W-9 name may correctly match a payee rather than the
legal owner. A Letter of Authorization supplies the evidence when a different
person signs the relevant landlord documents.

## What the first implementation should check

The system should propose a move-in workflow whenever any core member arrives,
regardless of order. It should expect related records but never label a record
as noncompliant solely because context is still incomplete.

It can flag, for human review:

- a stated rent, deposit, address/unit, move-in date, or lease term that
  conflicts across records;
- a lease without a corresponding move-in workflow, or a workflow without a
  lease;
- a W-9 that cannot be connected to a recorded payee or an unresolved payee;
- an owner/signature mismatch that has no supporting authorization evidence;
- an ownership verification that cannot be connected to the property/owner;
- a habitability record that does not approve the relevant property.

The current implementation compares the first safe group of shared fields:
property address, unit, monthly rent, security deposit, move-in date, and
lease term. Currency formatting is normalized, so `$1,850` and `$1,850.00`
agree; a genuine amount difference stays visible as a local correction finding.

It must not silently choose a “correct” value, merge people or businesses by
name alone, assume all signature dates should match, or send anything to HMIS,
Accounting, email, or another system.

## Readiness

The default prompt mode is off. When enabled later, the workflow may show a
quiet state such as `in progress`, `needs review`, or `complete for local
review`.

“Ready for HMIS” and “ready for Accounting” are intentionally deferred. Those
states should be activated only after the agency confirms the actual
destination-specific checklist, including which documents are conditional and
who must approve the package.
