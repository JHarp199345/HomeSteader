"""Local macOS Vision OCR for image-only PDF scans."""

from __future__ import annotations

from pathlib import Path
import platform
import shutil
import subprocess
from tempfile import TemporaryDirectory


def recognize_pdf_with_vision(source: Path) -> tuple[str, str | None]:
    if platform.system() != "Darwin":
        return "", "Local OCR is available only on macOS."
    renderer = shutil.which("pdftoppm")
    if not renderer:
        return "", "Local PDF rendering is not available, so OCR could not start."
    try:
        from Foundation import NSURL
        from Vision import VNImageRequestHandler, VNRecognizeTextRequest, VNRequestTextRecognitionLevelAccurate
    except ImportError:
        return "", "macOS Vision support is not installed, so OCR could not start."
    with TemporaryDirectory(prefix="homesteader-ocr-") as temporary_directory:
        prefix = Path(temporary_directory) / "page"
        try:
            subprocess.run([renderer, "-r", "200", "-png", str(source), str(prefix)], check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as error:
            return "", f"PDF could not be rendered for local OCR: {error}"
        pages = []
        for image_path in sorted(Path(temporary_directory).glob("page-*.png")):
            lines: list[str] = []
            def completed(request, error) -> None:
                if not error:
                    for observation in request.results() or []:
                        candidates = observation.topCandidates_(1)
                        if candidates:
                            lines.append(str(candidates[0].string()))
            request = VNRecognizeTextRequest.alloc().initWithCompletionHandler_(completed)
            request.setRecognitionLevel_(VNRequestTextRecognitionLevelAccurate)
            request.setUsesLanguageCorrection_(True)
            handler = VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(str(image_path)), None)
            try:
                success, error = handler.performRequests_error_([request], None)
            except Exception as error:
                return "", f"macOS Vision could not read the scan: {error}"
            if not success:
                return "", f"macOS Vision could not read the scan: {error or 'unknown error'}"
            if lines:
                pages.append("\n".join(lines))
    text = "\n\n".join(pages).strip()
    return (text, None) if text else ("", "Local OCR completed but found no readable text.")
