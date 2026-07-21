# AI proposal contract

An optional AI host may propose classifications and extracted facts for a deliberately selected staging job. Homesteader itself does not call a provider or expose a network endpoint.

## Required JSON shape

```json
{
  "document_id": "local-document-id",
  "provider_id": "gemini-workspace",
  "document_type": "contact_information",
  "overall_confidence": 0.97,
  "facts": [
    {
      "field": "hmis_id",
      "value": "H-TLS-000042",
      "evidence": "HMIS ID #: H-TLS-000042",
      "confidence": 0.99
    }
  ],
  "uncertainties": ["No readable signature"]
}
```

## Local validation rule

Homesteader records the host/provider identity and confidence, but it does not treat either as proof. Every proposed fact must include a quoted evidence fragment found in the stored source text. Invalid evidence is rejected. Valid proposals are queued for review; they do not automatically write identity facts or create relationships.

For handwritten scans, a proposal may set `evidence_type` to `visual_evidence`.
That means the fact was read from the preserved original image rather than from
the local OCR text. Visual facts are still review-only: they cannot directly
modify identity, schedules, or relationships.

This contract is shared by manual Gemini-for-Mac use, future API adapters, ChatGPT, Claude, or local models.
