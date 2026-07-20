# Assurance model: intelligence proposes; the record decides

Homesteader is built on the assumption that an AI can be articulate, confident, and wrong. Its confidence score is useful evidence, but it is never enough by itself to establish a consequential identity or relationship.

## Separate the decisions

The system must not collapse these into one action:

1. **Document classification:** What kind of thing is this? (blank consent form, lease, invoice, case note)
2. **Entity association:** Who, what property, unit, program, or case does it concern?
3. **Relationship decision:** Should it modify, support, replace, or belong to an existing record?

An AI may correctly classify a document as a consent form while lacking enough evidence to decide whether it concerns Jasmine, Lupita, or anyone at all.

## Fact classes

| Class | Meaning | Can it auto-commit an identity link? |
|---|---|---|
| Source fact | Clear text in the original record, such as an HMIS/client ID, full name, unit, signed date, or explicit reference. | Yes, if required hard constraints agree. |
| System-derived fact | A deterministic consequence of confirmed records, such as the active tenant of a known unit. | Sometimes; it must remain explainable. |
| AI proposal | Extraction, similarity match, signature guess, handwriting interpretation, or semantic inference. | No, not by itself. |
| Human correction | A user explicitly assigns or corrects the relationship. | Yes; it becomes a local precedent with provenance. |

## Decision policy

1. A conflict in hard identifiers always routes to review.
2. A high AI confidence score never overrides missing or conflicting hard identifiers.
3. A signature image or a partial/surname-only match is supporting evidence, never a sole identity key.
4. Automatic linking requires the domain module's full set of hard constraints. For the lease prototype: tenant, property, unit, and referenced lease date.
5. Otherwise, create a proposal in review with the candidate(s), evidence, and the smallest question needed from the user.
6. A human correction records a new ledger event; it does not erase the original AI proposal or source file.

## Learning from corrections

The system should learn locally from corrections as **explicit precedents**, not hidden model memory:

```text
AI proposal: consent form → Lupita Martinez (rejected)
Human correction: consent form → Jasmine Morales (confirmed)
Reason: user selected the correct active participant
```

Future matching may use that correction as a local preference, but a new document still must pass hard-constraint and conflict checks. One correction must not become permission to misfile every similar record.

## User experience

The review view should say what the system knows and what it does not:

> This appears to be a completed consent form. I found two possible participants. The signature is not enough to choose safely. Is this Jasmine Morales or Lupita Martinez?

The human supplies intent; the system records it and keeps the evidence trail.
