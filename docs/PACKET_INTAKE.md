# Packet Intake Model

## Purpose

A packet is one deliberate intake event: for example, a new-client enrollment bundle or a quarterly recertification bundle. It may contain several PDFs and scans, and the documents may not arrive in a reliable order. Homesteader preserves every source file, then uses the entire packet's evidence to reduce manual filing without silently inventing a client relationship.

## Processing order

1. Create an immutable intake packet with its received time, source-file hashes, and document IDs.
2. Reject an exact source-file hash as an already-seen occurrence. Record the new occurrence, but do not store or file the same scan twice.
3. Extract and retain each document's facts independently, including whether text came from an embedded PDF layer or local Vision OCR.
4. Find identity anchors anywhere in the packet: HMIS ID, CHAMP ID, then a consistent name plus date of birth.
5. Create or find the client record from strong evidence. Documents that contain no identifier are not treated as separate clients merely because they were scanned first.
6. For every remaining document, attach it automatically only when its stated identity agrees with the single packet anchor and it has no conflicting identifier. OCR-derived documents receive a proposed client and remain in review until a person confirms them.
7. Keep ambiguous, conflicting, unreadable, or identity-free documents in review with the packet client as a visible candidate when one exists.

## Client creation

A client can be created from a document containing an HMIS or CHAMP identifier even when the other documents in the packet have only the client name, signature, date, program, or other supporting facts. The source identities remain distinct through the HMIS-to-CHAMP transition; a human-confirmed relationship joins their umbrella view rather than erasing either source history.

## Duplicate and recurrence rules

- Exact same source bytes: duplicate occurrence, never a second filed document.
- Same document type and same client, with the same reporting period or document date: possible duplicate or corrected version, held for review.
- Same document type and same client, with a later reporting period or later stated document date: a new chronological occurrence. It belongs beside the earlier packet, not in place of it.
- Similar text alone is never enough to discard a document. Recurring forms frequently differ only in dates, income amounts, signatures, or small factual changes.

## Packet safeguards

- Packet order is useful context, never identity proof.
- A conflicting HMIS or CHAMP ID blocks automatic association.
- A scan read by OCR never bypasses human confirmation for client assignment.
- Each packet decision and manual override is recorded in the local event history.
- Original files remain available and are never renamed as the evidence record.

## First implementation slice

1. Add a packet record and a packet-aware inbox action that processes only unprocessed source hashes.
2. Determine a single strong client anchor across all newly seen documents.
3. Add that anchor as a proposed client on related review items, rather than automatically filing OCR-derived scans.
4. Let the review screen accept the proposal with one action, creating the client/document relationship event.
5. Add packet and quarterly-recurrence fixtures before enabling automatic association for any additional document types.
