# Gemini desktop bridge: selected access, no Homesteader API

The Gemini Mac app can be the first AI host without requiring Homesteader to expose a public or network API. The first integration is a local, user-controlled file workflow.

## Access shape

Do **not** point Gemini at the Homesteader state file or give it an unrestricted database folder. Instead, Homesteader creates selected, task-specific artifacts in a local staging folder:

```text
ai_staging/
  2026-07-20-consent-form-001/
    source-document.pdf
    context.txt
    classification-request.md
```

The user chooses that artifact in Gemini for Mac. Gemini receives the selected document and request, not unrelated case files, the ledger database, or arbitrary local folders.

## Response contract

Gemini is asked to return structured output that distinguishes:

- source facts and quotations;
- document classification;
- candidate entities and evidence;
- unresolved ambiguity;
- proposed relationships;
- confidence for each individual claim.

Homesteader later imports the response into a proposal queue. It validates hard constraints and routes unresolved identity decisions to review.

## Why this is the first bridge

- Uses the work Gemini app and its existing account access.
- Requires no API key, public endpoint, or programmatic access to Gemini.
- Makes the selected disclosure understandable to the user.
- Keeps the Homesteader database local.
- Lets the same request/response contract later power an API adapter or another host such as ChatGPT or Claude.

The staged-folder workflow is the first product path. Any future deeper desktop integration should be added only after the app exposes a stable, approved capability that can honor this same selected-access model.
