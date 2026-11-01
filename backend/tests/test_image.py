"""Image validation, QR decoding and honest partial-result tests."""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image


def _qr_png(text: str) -> bytes:
    encoder = cv2.QRCodeEncoder_create()
    matrix = encoder.encode(text)
    canvas = cv2.copyMakeBorder(matrix, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    canvas = cv2.resize(canvas, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
    ok, buffer = cv2.imencode(".png", canvas)
    assert ok
    return buffer.tobytes()


def _plain_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (240, 120), (245, 245, 245)).save(buffer, format="PNG")
    return buffer.getvalue()


def _upload(client, data, headers, filename="image.png"):
    return client.post(
        "/api/scan/image",
        data={"file": (io.BytesIO(data), filename)},
        headers=headers,
        content_type="multipart/form-data",
    )


def test_qr_image_is_decoded(client, app, auth):
    app.config["MAX_EXTRACTED_URLS_IMAGE"] = 0  # avoid outbound URL scanning in this test
    response = _upload(client, _qr_png("https://example.com/verify"), auth["headers"])
    assert response.status_code == 201, response.get_json()
    data = response.get_json()["data"]
    assert data["analysis"]["qr_values"] == ["https://example.com/verify"]
    assert data["analysis"]["file"]["actual_format"] == "PNG"
    assert data["analysis"]["extracted_urls"] == ["https://example.com/verify"]
    stages = {stage["name"]: stage["status"] for stage in data["analysis"]["stages"]}
    assert stages["Image validation"] == "completed"
    assert stages["QR decoding"] == "completed"
    assert stages["OCR extraction"] in {"unavailable", "completed"}


def test_plain_image_without_ocr_is_inconclusive(client, auth):
    response = _upload(client, _plain_png(), auth["headers"])
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["analysis"]["content_extracted"] is False
    assert data["classification"] == "unknown"
    assert any("OCR" in limitation for limitation in data["analysis"]["limitations"])
    assert any("no guarantee" not in action.lower() for action in data["analysis"]["assessment"]["recommended_actions"])


def test_invalid_image_rejected(client, auth):
    response = _upload(client, b"this is not an image", auth["headers"], filename="fake.png")
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "invalid_image"


def test_svg_rejected(client, auth):
    response = _upload(
        client,
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        auth["headers"],
        filename="image.svg",
    )
    assert response.status_code == 422


def test_empty_upload_rejected(client, auth):
    response = _upload(client, b"", auth["headers"])
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "empty_file"


def test_oversized_upload_rejected(client, app, auth):
    app.config["MAX_IMAGE_BYTES"] = 100
    response = _upload(client, _plain_png(), auth["headers"])
    assert response.status_code == 413
    assert response.get_json()["error"]["code"] == "file_too_large"


def test_missing_file_rejected(client, auth):
    response = client.post("/api/scan/image", data={}, headers=auth["headers"], content_type="multipart/form-data")
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "missing_file"
