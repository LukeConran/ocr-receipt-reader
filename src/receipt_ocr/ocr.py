"""Local OCR backends: Tesseract by default, Apple Vision on macOS when present."""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from receipt_ocr.preprocess import preprocess_for_ocr

log = logging.getLogger(__name__)

# Keep this shlex-safe (no quotes). PSM 6 = assume a uniform block of text.
TESSERACT_CONFIG = "--oem 3 --psm 6"


class OCRError(RuntimeError):
    pass


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def vision_available() -> bool:
    if platform.system() != "Darwin":
        return False
    try:
        import Vision  # noqa: F401
        import Quartz  # noqa: F401
        from Foundation import NSData  # noqa: F401
    except Exception:
        return False
    return True


def describe_ocr_backend(engine: str = "auto") -> str:
    engine = (engine or "auto").lower()
    if engine == "vision":
        return "Apple Vision" if vision_available() else "Apple Vision (unavailable)"
    if engine == "tesseract":
        return "Tesseract" if tesseract_available() else "Tesseract (unavailable)"
    if vision_available():
        return "Apple Vision"
    if tesseract_available():
        return "Tesseract"
    return "none"


def _ocr_tesseract(image_bgr: np.ndarray) -> str:
    try:
        import pytesseract
    except ImportError as exc:
        raise OCRError(
            "pytesseract is not installed. Recreate the venv with ./run.sh"
        ) from exc
    if not tesseract_available():
        raise OCRError(
            "Tesseract is not on PATH. On a Mac: brew install tesseract"
        )
    processed = preprocess_for_ocr(image_bgr)
    pil = Image.fromarray(processed)
    try:
        text = pytesseract.image_to_string(pil, lang="eng", config=TESSERACT_CONFIG)
    except pytesseract.TesseractError as exc:
        raise OCRError(f"Tesseract failed: {exc}") from exc
    return text or ""


def _bgr_to_png_bytes(image_bgr: np.ndarray) -> bytes:
    import cv2

    ok, encoded = cv2.imencode(".png", image_bgr)
    if not ok:
        raise OCRError("Could not encode the captured frame")
    return encoded.tobytes()


def _ocr_vision(image_bgr: np.ndarray) -> str:
    """Apple Vision text recognition. Requires PyObjC Vision + Quartz."""
    try:
        import Vision
        from Foundation import NSData, NSArray
    except Exception as exc:
        raise OCRError(
            "Apple Vision is not available. pip install pyobjc-framework-Vision "
            "pyobjc-framework-Quartz  (macOS only)"
        ) from exc

    png = _bgr_to_png_bytes(image_bgr)
    data = NSData.dataWithBytes_length_(png, len(png))
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    try:
        request.setUsesLanguageCorrection_(True)
    except Exception:
        pass
    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
    ok, error = handler.performRequests_error_(NSArray.arrayWithObject_(request), None)
    if not ok:
        raise OCRError(f"Apple Vision failed: {error}")
    observations = request.results() or []
    lines: list[str] = []
    for obs in observations:
        candidates = obs.topCandidates_(1)
        if not candidates:
            continue
        lines.append(str(candidates[0].string()))
    return "\n".join(lines)


def image_to_text(image_bgr: np.ndarray, engine: str = "auto") -> str:
    """OCR a BGR OpenCV image. ``engine`` is auto | tesseract | vision."""
    if image_bgr is None or getattr(image_bgr, "size", 0) == 0:
        raise OCRError("Empty image")
    choice = (engine or "auto").lower()
    if choice == "vision":
        return _ocr_vision(image_bgr)
    if choice == "tesseract":
        return _ocr_tesseract(image_bgr)
    if vision_available():
        try:
            return _ocr_vision(image_bgr)
        except OCRError as exc:
            log.warning("Vision OCR failed, falling back to Tesseract: %s", exc)
    return _ocr_tesseract(image_bgr)


def tesseract_version() -> str | None:
    exe = shutil.which("tesseract")
    if not exe:
        return None
    try:
        out = subprocess.check_output([exe, "--version"], text=True, stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.splitlines()[0].strip() if out else None


def load_image_bgr(path: str | Path) -> np.ndarray:
    import cv2

    image = cv2.imread(str(path))
    if image is None:
        raise OCRError(f"Could not read image: {path}")
    return image
