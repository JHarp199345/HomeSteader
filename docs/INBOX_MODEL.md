# Inbox model

The inbox is a local holding area for unsorted records. It is deliberately not a folder taxonomy.

## User flow

1. Place an item in `inbox/`, scan it, or capture it from a future interface.
2. Homesteader records the original source, detects duplicates, and extracts what it can.
3. The engine either files it to known entities/ledgers or creates a concise review item.
4. The original source remains available; filing metadata is always reversible.

## Generic intake fields

Every intake item needs only these universal fields:

- original file or message;
- acquisition time and source route;
- content hash;
- extracted text when available;
- user-supplied context note, if needed;
- domain module used to interpret it;
- processing status.

The domain module determines domain-specific entities and ledgers. Property operations may recognize leases, units, tenants, addenda, maintenance cases, and vendors. Case management may recognize participants, programs, assessments, referrals, and case notes.

## Ambiguous documents

Some records cannot identify themselves. A photo of a wall, an isolated text screenshot, or a handwritten note can enter the inbox with a one-sentence typed or voice context note, such as:

> “Water stain at Unit 1B, reported by Elena today.”

That note is explicit user provenance—not an AI guess. Homesteader should ask for the smallest useful clarification only when it cannot safely associate the item.
