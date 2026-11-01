"""Unified image pipeline: validation, QR decoding, OCR and URL enrichment."""

from __future__ import annotations

import hashlib
import io
import re
import threading
import warnings
from typing import Any

from flask import current_app
from PIL import Image, UnidentifiedImageError

from ..detection.email_heuristics import analyze_email_text
from ..utils.text import extract_urls
from .url_enrichment import analyze_extracted_urls

ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP", "GIF", "BMP", "TIFF"}
_BARE_URL_RE = re.compile(
    r"(?i)^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}(?::\d{1,5})?(?:/[^\s]*)?$"
)

_ocr_lock = threading.Lock()
_ocr_reader = None
_ocr_status: dict[str, Any] = {"checked": False, "available": False, "reason": ""}


class InvalidImage(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _get_ocr_reader() -> dict[str, Any]:
    global _ocr_reader, _ocr_status  # noqa: PLW0603
    with _ocr_lock:
        if _ocr_status["checked"]:
            return _ocr_status
        _ocr_status = {"checked": True, "available": False, "reason": "OCR is disabled by configuration."}
        if not current_app.config.get("ENABLE_OCR", False):
            return _ocr_status
        try:
            import easyocr  # type: ignore
        except Exception:
            _ocr_status = {
                "checked": True,
                "available": False,
                "reason": "EasyOCR is not installed. Install it and enable ENABLE_OCR to use OCR.",
            }
            return _ocr_status
        try:
            _ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            _ocr_status = {"checked": True, "available": True, "reason": ""}
        except Exception:
            _ocr_status = {
                "checked": True,
                "available": False,
                "reason": "OCR models could not be initialised (model download may be required).",
            }
        return _ocr_status


def _decode_qr(array) -> tuple[list[str], str]:
    try:
        import cv2
    except Exception:
        return [], "OpenCV is not installed, so QR decoding is unavailable."

    texts: list[str] = []
    try:
        detector = cv2.QRCodeDetector()
        ok, decoded, _points, _straight = detector.detectAndDecodeMulti(array)
        if ok and decoded:
            texts.extend(value for value in decoded if value)
    except Exception:
        pass
    if not texts:
        try:
            detector = cv2.QRCodeDetector()
            value, _points, _straight = detector.detectAndDecode(array)
            if value:
                texts.append(value)
        except Exception:
            pass

    try:
        from pyzbar.pyzbar import decode as zbar_decode  # type: ignore

        from PIL import Image as PILImage

        for symbol in zbar_decode(PILImage.fromarray(array)):
            try:
                value = symbol.data.decode("utf-8", errors="replace")
            except Exception:
                continue
            if value and value not in texts:
                texts.append(value)
    except Exception:
        # Optional dependency; OpenCV already attempted decoding.
        pass

    unique = list(dict.fromkeys(text.strip()[:2000] for text in texts if text.strip()))
    if unique:
        return unique, f"{len(unique)} QR code value(s) decoded."
    return [], "No QR code was decoded. The image may not contain a QR code or may be low quality."


def _run_ocr(image: Image.Image) -> tuple[str, dict[str, Any]]:
    status = _get_ocr_reader()
    if not status["available"]:
        return "", status
    try:
        import numpy as np

        with _ocr_lock:
            results = _ocr_reader.readtext(np.array(image), detail=0, paragraph=True)  # type: ignore[union-attr]
        text = "\n".join(str(item) for item in results)[:8000]
        if text.strip():
            return text, {"checked": True, "available": True, "reason": ""}
        return "", {"checked": True, "available": True, "reason": "OCR completed but found no text."}
    except Exception:
        return "", {
            "checked": True,
            "available": False,
            "reason": "OCR failed while processing this image.",
        }


def _qr_urls(values: list[str]) -> list[str]:
    urls: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        if re.match(r"(?i)^https?://", cleaned):
            urls.append(cleaned)
        elif _BARE_URL_RE.match(cleaned):
            urls.append("https://" + cleaned)
    return urls


def analyze_image(data: bytes, filename: str, declared_type: str) -> dict[str, Any]:
    config = current_app.config
    max_bytes = int(config.get("MAX_IMAGE_BYTES", 5 * 1024 * 1024))
    if not data:
        raise InvalidImage("empty_file", "The uploaded file is empty.")
    if len(data) > max_bytes:
        raise InvalidImage("file_too_large", f"The image must be {max_bytes // (1024 * 1024)} MB or smaller.")

    Image.MAX_IMAGE_PIXELS = int(config.get("MAX_IMAGE_PIXELS", 25_000_000))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            probe = Image.open(io.BytesIO(data))
            actual_format = (probe.format or "").upper()
            probe.verify()
        image = Image.open(io.BytesIO(data))
        image.load()
        if getattr(image, "is_animated", False):
            image.seek(0)
        width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise InvalidImage(
            "invalid_image",
            "The file is not a readable image or is corrupted.",
        )
    except Image.DecompressionBombWarning:
        raise InvalidImage("image_too_large", "The image dimensions exceed the safe processing limit.")
    except Exception:
        raise InvalidImage("invalid_image", "The image could not be processed.")

    if actual_format not in ALLOWED_FORMATS:
        raise InvalidImage(
            "unsupported_format",
            "Unsupported image format. Use PNG, JPEG, WEBP, GIF, BMP or TIFF.",
        )
    if width * height > int(config.get("MAX_IMAGE_PIXELS", 25_000_000)):
        raise InvalidImage("image_too_large", "The image dimensions exceed the safe processing limit.")

    rgb = image.convert("RGB")
    analysis_image = rgb.copy()
    analysis_image.thumbnail((2000, 2000))
    import numpy as np

    array = np.array(analysis_image)
    qr_values, qr_detail = _decode_qr(array)
    ocr_text, ocr_status = _run_ocr(analysis_image)

    extracted_text = "\n".join([*qr_values, ocr_text]).strip()[:8000]
    text_urls = extract_urls(extracted_text, limit=10)
    qr_candidates = _qr_urls(qr_values)
    urls = list(dict.fromkeys([*qr_candidates, *text_urls]))

    findings: list[dict[str, Any]] = []
    stages: list[dict[str, Any]] = [
        {
            "name": "Image validation",
            "status": "completed",
            "detail": (
                f"Validated {actual_format} image ({width}×{height}px, {len(data)} bytes). "
                "The client-declared MIME type was not trusted."
            ),
        },
        {
            "name": "QR decoding",
            "status": "completed",
            "detail": qr_detail,
        },
        {
            "name": "OCR extraction",
            "status": (
                "completed"
                if ocr_status.get("available")
                else ("unavailable" if ocr_status.get("checked") else "failed")
            ),
            "detail": (
                f"{len(ocr_text)} characters of text extracted."
                if ocr_status.get("available")
                else ocr_status.get("reason", "OCR unavailable.")
            ),
        },
    ]
    limitations: list[str] = [
        "QR and OCR extraction depend on image quality, resolution and installed optional components.",
        "The image was not executed and no reverse-image or visual brand detection was performed.",
    ]
    if not ocr_status.get("available"):
        limitations.append(
            f"OCR is unavailable: {ocr_status.get('reason', 'not configured')}. Text visible in a "
            "screenshot cannot be assessed without OCR."
        )

    if extracted_text:
        text_analysis = analyze_email_text("", "", extracted_text)
        findings.extend(text_analysis["signals"])
        stages.append(
            {
                "name": "Text heuristics (extracted content)",
                "status": "completed",
                "detail": f"{len(text_analysis['signals'])} indicator(s) from extracted text.",
            }
        )
        if text_analysis["signals"]:
            limitations.append(
                "Text found in an image may be misread by OCR; verify the quoted text against the image."
            )
    else:
        stages.append(
            {
                "name": "Text heuristics (extracted content)",
                "status": "skipped",
                "detail": "No text was extracted from the image.",
            }
        )

    enrichment = analyze_extracted_urls(
        urls,
        limit=int(config.get("MAX_EXTRACTED_URLS_IMAGE", 3)),
        source_label="image QR or OCR content",
    )
    findings.extend(enrichment["findings"])
    stages.append(enrichment["stage"])
    limitations.extend(enrichment["limitations"])

    if qr_values and not urls:
        limitations.append("QR content was decoded but no URL was found in it.")
    if not qr_values:
        limitations.append("No QR code was detected in the image.")

    content_extracted = bool(extracted_text)

    return {
        "file": {
            "filename": filename[:200],
            "declared_type": (declared_type or "")[:120],
            "actual_format": actual_format,
            "width": width,
            "height": height,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "analysis_max_dimension": max(analysis_image.size),
        },
        "qr_values": qr_values,
        "ocr_text": ocr_text[:4000],
        "extracted_text": extracted_text[:4000],
        "extracted_urls": urls,
        "signals": findings,
        "url_results": enrichment["results"],
        "stages": stages,
        "limitations": list(dict.fromkeys(limitations)),
        "content_extracted": content_extracted,
        "input_type_detail": "qr_code" if qr_values else "screenshot",
    }
