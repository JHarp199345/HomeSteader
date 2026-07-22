# Hateful Eight fictional training matrix

This corpus is intentionally difficult. It contains only invented data and is
for local Homesteader testing—not submission, HMIS, CHAMP, or staff training
records.

Run every numbered folder using a fresh Homesteader state unless the test says
to continue from the prior run. The source profiles are a reference set; the
numbered folders are the uploads.

| Run | Upload | Expected behavior |
| --- | --- | --- |
| 01 | Complete documents from eight PTCs in shuffled order | Build eight distinct files; preserve property, landlord, unit, program, HMIS, and date relationships without treating scan order as identity proof. |
| 02 | Partial, out-of-order records | Keep unanchored material in review or as a provisional file; identify missing packet evidence and applicable schedule records without inventing a history. |
| 03 | Follow-up missing material and a completed revision | Attach later records to the existing file when identity is supported. Propose a `supersedes_for_fields` relationship for Devin's completed quarterly record, while retaining the incomplete original. |
| 04 | Exact byte-for-byte repeated uploads | Identify every second copy by raw hash. Do not create a second periodic ledger entry or delete the original. |

## Identity collision cases

- **Jasmine Morales** exists twice. `H-TRAIN-0003` has DOB `05/09/1990`; `H-TRAIN-0004` has DOB `11/30/1996`. Name alone must never merge their files.
- **Morgan Lee** and **Casey Reed** share DOB `02/18/1991`, but have different HMIS IDs and names. DOB alone must never merge their files.
- **Devin Cross** first has a quarterly record with the HMIS field omitted. The completed version arrives later with the same date and content plus `H-TRAIN-0007`. This is a revision candidate, not a true duplicate and not a reason to erase the incomplete source.

## Evidence criteria

The corpus passes only if Homesteader remains both useful and cautious:

1. Strong identifiers beat names, birth dates, scan order, and resemblance.
2. Name-only or incomplete records are not confidently assigned merely because a convenient profile exists.
3. A later, more complete source can become the preferred export evidence for the affected fields, but the old source and its ledger event persist.
4. Missing documents are reported as missing local evidence, never manufactured.
5. A repeated raw file produces a duplicate-review outcome—not another client, event, or income period.
6. Reverse search still finds the correct network through landlord, property, unit, and participant values after a shuffled upload.
