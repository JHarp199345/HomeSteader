# Information extraction protocol

Every intake route—rules, OCR, Gemini, ChatGPT, Claude, or a local model—must return the same evidence-backed facts.

```json
{
  "field": "date_of_birth",
  "value": "1990-01-01",
  "evidence": "Date of birth: 1990-01-01",
  "provenance": "document_text",
  "confidence": 1.0
}
```

The key is not the confidence number. Each value states what it is, where it came from, and how certain the extractor was.

## Core fact vocabulary

- participant/client/tenant name;
- program;
- date of birth or approved participant identifier;
- document date and reporting period;
- contact information, emergency contacts, and care providers;
- address/unit/property;
- signatures and document references.

Domain modules extend this vocabulary. Property management adds units, leases, vendors, appliances, and warranties. Case management adds enrollment, assessment, referral, consent, and program fields.

## Decision sequence

1. Preserve the original document.
2. Extract facts with source evidence.
3. Classify the document.
4. Resolve candidate entities using hard identifiers first and supporting facts second.
5. File, create a proposal, or request review.
6. Record the decision and provenance in the ledger.

Two distinct people with the same available facts cannot be resolved truthfully by cleverness alone. The system must preserve the collision and request an external identifier or human decision.
