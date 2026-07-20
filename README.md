# Homesteader

Homesteader is a local-first, open-source framework for turning unsorted documents into a searchable record of entities, evidence, and chronological ledgers.

It starts with property records, but the core is deliberately domain-neutral: a later case-management module can model participants, programs, assessments, and referrals using the same intake, provenance, relationship, and review systems.

## Safety boundary

This repository currently uses **fictional plain-text fixtures only**. Do not add client, tenant, health, HMIS, or employer records here. Before Homesteader handles real workplace records, it needs approved storage, access control, retention, encryption, audit, and organizational-policy decisions. A local file is not automatically an authorized records system.

The core has no web endpoint or outbound network behavior. It is local-only by default. Users may later configure an approved AI provider or use an approved work AI application manually; Homesteader must never silently grant broad database access. See [the security model](docs/SECURITY_MODEL.md).

## First proof of concept

The first milestone is intentionally narrow:

1. Ingest a fictional lease.
2. Ingest a differently formatted addendum later.
3. Extract the relevant facts.
4. Link the addendum to the lease only when the evidence is strong.
5. Preserve the source, explanation, confidence score, and an append-only ledger event.
6. Put an intentionally ambiguous document in **Needs Review** rather than guessing.

## Run it

Requires Python 3.11+ and no external packages.

```bash
python3 -m unittest discover -s tests -v
python3 -m homesteader.cli --state data/demo.json ingest fixtures/lease_elena_ramirez.txt
python3 -m homesteader.cli --state data/demo.json ingest fixtures/pet_addendum_elena_ramirez.txt
python3 -m homesteader.cli --state data/demo.json status
python3 -m homesteader.cli inbox
```

The prototype supports plain-text fixtures only. PDF/image OCR, local-model adapters, secure sync, and a user interface are planned next layers—not implied capabilities of this first proof.

## Current structure

- `homesteader/` — local prototype code
- `fixtures/` — fictional documents used to test the model
- `expected_results/` — intended outcomes of the fixtures
- `tests/` — automated checks
- `docs/` — technical and product decisions
- `PROJECT_PLAN.md` — product roadmap

## Core model

- **Entities** are durable identities: properties, units, people, leases, vendors, programs, participants, and assets.
- **Evidence** is the preserved original item plus extracted metadata.
- **Ledgers** are append-only chronological events affecting an entity or workflow.
- **Relationships** are explicit, provenance-carrying links such as `modifies`, `documents`, or `responds_to`.

The engine must separate confirmed source facts, derived relationships, and unconfirmed AI hypotheses. Automated links must be explainable and reversible.

## Sorting before AI

AI is an enhancement, not a prerequisite. The first sorting pass uses observable characteristics: document wording, completed identity fields, signatures, dates, repeated records, and content hashes. An unfilled consent form belongs in a reusable **Form Bank**, not an unknown client file. Exact duplicate uploads are detected using a content hash and retained as a single original record with a duplicate event.

Near duplicates—such as a rescan with different whitespace or punctuation—are held as review candidates rather than silently discarded. See [the batch inference model](docs/BATCH_INFERENCE_MODEL.md) for how local pre-processing and a frontier model work together on a selected backlog.

Recurring records are tracked as time-based ledger events, not merged merely because their content or amounts resemble a previous submission. Undated sources remain explicitly undated; see [temporal provenance](docs/TEMPORAL_PROVENANCE.md).
