"""Consistent JSON response envelopes and API errors."""

from __future__ import annotations

from typing import Any

from flask import jsonify


class ApiError(Exception):
    """Raised for expected, user-facing API failures."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


def success(data: Any = None, message: str | None = None, status: int = 200, meta: dict | None = None):
    payload: dict[str, Any] = {"success": True, "data": data}
    if message:
        payload["message"] = message
    if meta is not None:
        payload["meta"] = meta
    return jsonify(payload), status


def failure(
    code: str,
    message: str,
    status: int = 400,
    details: Any = None,
):
    payload: dict[str, Any] = {
        "success": False,
        "error": {"code": code, "message": message},
    }
    if details is not None:
        payload["error"]["details"] = details
    return jsonify(payload), status
