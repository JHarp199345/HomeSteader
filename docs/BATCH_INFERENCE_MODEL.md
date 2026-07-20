# Batch inference model: frontier intelligence without unrestricted access

The staging folder is not a one-document throttle. It is a **job boundary**: a selected, coherent batch that can be analyzed together by a capable AI system.

## Why batches matter

Many documents are ambiguous alone but become clear together:

- a consent form, program enrollment, and case note may identify the same participant;
- several scans may reveal they are copies or versions of one form;
- an addendum may identify its lease only when the original lease is in the batch;
- a group of invoices may show a repeated vendor and maintenance issue.

Homesteader should use model context deliberately: provide the model with related source documents, a concise snapshot of candidate entities, and domain rules. The model can then propose relationships across the full batch instead of treating each upload in isolation.

## Batch workflow

```text
Unsorted backlog
    ↓
Local pre-processing
  • hashes / exact duplicates
  • near-duplicate candidates
  • basic document characteristics
  • known local entity candidates
    ↓
User selects a coherent batch
    ↓
Staging job
  • source files
  • manifest of document IDs and hashes
  • narrow context snapshot
  • domain rules / output schema
    ↓
Frontier AI (Gemini, ChatGPT, Claude, or local model)
    ↓
Structured proposals for every document + cross-document links
    ↓
Local validation
  • hard constraints
  • conflicts
  • confidence by claim
  • review queue
    ↓
Ledger events and confirmed records
```

## The batch manifest

A future staging job should contain a machine-readable manifest such as:

```json
{
  "job_id": "case-backlog-2026-07-20-01",
  "domain": "case_management",
  "documents": [
    {"id": "doc-01", "file": "consent.pdf", "sha256": "...", "near_duplicate_candidates": ["doc-04"]},
    {"id": "doc-02", "file": "enrollment.pdf", "sha256": "..."}
  ],
  "candidate_entities": ["Jasmine Morales", "Lupita Martinez"],
  "rules": "Never assign a person based on signature similarity alone. Return ambiguity explicitly."
}
```

## Parallelism without blind automation

The AI can process hundreds of selected documents concurrently in one batch context or through parallel requests. Homesteader’s job is not to slow it down; it is to give it the relevant context and ensure each proposal remains traceable to specific evidence.

Batch size should be configurable for the selected model’s practical file/context limits. Large backlogs can be partitioned by a meaningful boundary—program, property, date range, or document cluster—while duplicate candidates and shared entities can bridge batches.

## Core rule

The frontier model may see a broad, intentionally selected job. It does not need—and should not receive—unbounded access to every record just to infer relationships within that job.
