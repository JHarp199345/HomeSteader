# Prototype specification: lease-to-addendum linking

## Goal

Prove that Homesteader can turn two independently ingested fictional records into a safe, explainable relationship without asking the user to choose a folder or tag.

## Inputs

1. `lease_elena_ramirez.txt`: an original residential lease.
2. `pet_addendum_elena_ramirez.txt`: a later pet authorization addendum that explicitly modifies the lease.
3. `ambiguous_pet_addendum.txt`: a document lacking enough information to choose safely between possible leases.

## Required output

For every ingest, preserve the source text and compute a source hash. Extracted facts must remain separate from derived links.

For the first two documents, the system must create:

- tenant, property, unit, and lease entities;
- an append-only `lease_created` event;
- an append-only `document_linked` event;
- a `modifies` relationship from the addendum to the lease;
- a confidence score and the reasons used to establish the relationship.

For the ambiguous document, the system must produce a review item and create no `modifies` relationship.

## Matching policy for v0

This prototype is deterministic, deliberately conservative, and not an AI claim. A document can link automatically only when its tenant, property, unit, and referenced lease date match an existing lease. Any missing or conflicting hard identifier sends it to review.

Later versions may use a local or user-authorized model to extract information and rank candidates, but the application must continue to enforce hard constraints and record evidence.

## Out of scope

PDF parsing, OCR, image understanding, email ingestion, cloud providers, real records, vendor workflows, and synchronization.
