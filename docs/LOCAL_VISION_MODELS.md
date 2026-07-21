# Local vision-model review

Homesteader's logic remains responsible for identity, document matching,
timelines, duplicates, and record state. A local vision-capable model is used
only to propose a transcription and labeled facts from a **selected**
handwritten scan.

`tools/local_vision_propose.py` supports a loopback-only Ollama endpoint or an
LM Studio/OpenAI-compatible local endpoint. It accepts a selected image or PDF
packet; PDF pages are rendered locally before model staging. It refuses
non-local URLs and does not write to Homesteader. The model's JSON must be
imported separately, where it is validated and put into review.

Example with a selected fictional scan:

```bash
python tools/local_vision_propose.py selected-scan.jpg \
  --document-id LOCAL_DOCUMENT_ID \
  --model YOUR_VISION_MODEL \
  --provider ollama \
  --output /tmp/handwriting-proposal.json

.venv/bin/python -m homesteader.cli --state data/homesteader.json \
  import-ai-proposal /tmp/handwriting-proposal.json
```

Compare local models using the exact same scan and retain the output JSON. A
good model quotes only visible text, names uncertainty, and does not invent an
identity or a correction. A proposal remains review-only even if the model
reports high confidence.

For the fictional handwritten quarterly fixture, score an accepted proposal:

```bash
python tools/score_vision_proposal.py \
  /tmp/handwriting-proposal.json \
  fixtures/handwritten_quarterly_income_verification.expected.json
```

The scorecard separately reports controlled-type accuracy, required-field
accuracy, missing/incorrect values, forbidden claims, and the model's own
confidence. It is intentionally not an approval decision.

The staging tool also preserves the model's raw response beside the proposal.
If it violates the JSON contract, no proposal is written or imported; the raw
response is retained as a benchmark failure rather than silently repaired.
