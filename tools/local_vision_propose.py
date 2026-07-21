#!/usr/bin/env python3
"""Stage one selected scan with a local vision model; never modify Homesteader.

The generated JSON must be imported separately with Homesteader's local
validation command. Endpoints are restricted to loopback addresses so this
tool cannot send a scan to the public internet by configuration accident.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

PROMPT = """You are reading one handwritten or scanned Housing Services document.
Return JSON only. Do not infer facts that are not visible. Set document_type to
exactly one of: unknown, form_template, contact_information,
program_enrollment, consent_to_share, income_declaration,
income_verification, housing_record, lease, lease_addendum. Transcribe legible
text and propose only these facts when present: participant, hmis_id, program,
enrollment_date, document_date, reporting_period, date_of_birth, landlord,
property_address, unit. Each proposed fact must have a short visual evidence
description, for example 'Handwritten HMIS field reads H-000042'. Mark unclear
or ambiguous handwriting in uncertainties. Do not make an identity decision.

Required JSON:
{
  "document_type": "one allowed type from the list above",
  "overall_confidence": 0.0,
  "transcription": "best effort transcription",
  "facts": [{"field":"hmis_id","value":"H-000042","evidence":"Handwritten HMIS field reads H-000042","evidence_type":"visual_evidence","confidence":0.0}],
  "uncertainties": []
}"""


def loopback_endpoint(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in LOOPBACK_HOSTS:
        raise ValueError("Only a loopback local-model endpoint is permitted (localhost, 127.0.0.1, or ::1).")
    return value.rstrip("/")


def extract_content(response: dict, provider: str) -> str:
    if provider == "ollama":
        return response["message"]["content"]
    return response["choices"][0]["message"]["content"]


def local_images(source: Path, max_pages: int) -> tuple[list[Path], tempfile.TemporaryDirectory | None]:
    """Return selected images, rendering PDF pages locally when needed."""
    if source.suffix.casefold() != ".pdf":
        return [source], None
    temporary = tempfile.TemporaryDirectory(prefix="homesteader-vision-")
    prefix = Path(temporary.name) / "page"
    subprocess.run(["pdftoppm", "-png", "-r", "200", str(source), str(prefix)], check=True, capture_output=True)
    images = sorted(Path(temporary.name).glob("page-*.png"))[:max_pages]
    if not images:
        temporary.cleanup()
        raise ValueError("The selected PDF did not render to an image page.")
    return images, temporary


def request_completion(*, provider: str, endpoint: str, model: str, images: list[Path]) -> str:
    encoded = [base64.b64encode(image.read_bytes()).decode("ascii") for image in images]
    if provider == "ollama":
        url = f"{endpoint}/api/chat"
        payload = {
            "model": model, "stream": False, "format": "json", "think": False,
            "options": {"temperature": 0, "num_predict": 900},
            "messages": [{"role": "user", "content": PROMPT, "images": encoded}],
        }
    else:
        url = f"{endpoint}/chat/completions"
        payload = {
            "model": model,
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 900,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": PROMPT},
                *[{"type": "image_url", "image_url": {"url": f"data:image/{image.suffix.lstrip('.')};base64,{encoded_image}"}} for image, encoded_image in zip(images, encoded)],
            ]}],
        }
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=180) as response:  # noqa: S310 - endpoint is loopback-validated above
        raw = json.loads(response.read().decode("utf-8"))
    return extract_content(raw, provider)


def parse_model_json(content: str) -> dict:
    """Accept a plain JSON object or a fenced JSON object; reject anything else."""
    candidate = content.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(candidate)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a review-only proposal from one selected scan using a local vision model.")
    parser.add_argument("image", type=Path, help="Selected local image scan or PDF packet; PDF pages are rendered locally.")
    parser.add_argument("--document-id", required=True, help="Existing local Homesteader document ID; this tool does not create one.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--provider", choices=["ollama", "openai-compatible"], default="ollama")
    parser.add_argument("--endpoint", help="Loopback endpoint; defaults to Ollama :11434 or LM Studio/OpenAI-compatible :1234/v1")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=6, help="Maximum PDF pages to stage at once (default: 6).")
    args = parser.parse_args()
    if args.image.suffix.casefold() not in {".pdf", ".png", ".jpg", ".jpeg", ".heic", ".tif", ".tiff"}:
        parser.error("Use a selected image scan or PDF packet.")
    provider = args.provider
    default = "http://127.0.0.1:11434" if provider == "ollama" else "http://127.0.0.1:1234/v1"
    if args.max_pages < 1:
        parser.error("--max-pages must be at least 1.")
    images, temporary = local_images(args.image, args.max_pages)
    try:
        raw = request_completion(provider=provider, endpoint=loopback_endpoint(args.endpoint or default), model=args.model, images=images)
        raw_path = args.output.with_suffix(args.output.suffix + ".raw.txt")
        raw_path.write_text(raw)
        try:
            proposal = parse_model_json(raw)
        except json.JSONDecodeError as error:
            raise SystemExit(f"Model returned invalid JSON; preserved raw output at {raw_path}: {error}") from error
        proposal["document_id"] = args.document_id
        proposal["provider_id"] = f"local-{provider}:{args.model}"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(proposal, indent=2) + "\n")
        print(f"Wrote review-only proposal: {args.output} (raw response: {raw_path})")
    finally:
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    main()
