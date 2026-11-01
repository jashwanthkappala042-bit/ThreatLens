"""Serializers that define the public API shape."""

from __future__ import annotations

from typing import Any

from .detection.risk_engine import CLASSIFICATION_LABELS
from .models import Comment, CommunityPost, Scan, User
from .utils.text import iso


def user_public(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "is_admin": user.is_admin,
        "created_at": iso(user.created_at),
    }


def scan_summary(scan: Scan) -> dict[str, Any]:
    assessment = (scan.analysis or {}).get("assessment") or {}
    return {
        "id": scan.id,
        "input_type": scan.input_type,
        "input_label": scan.input_label,
        "input_preview": scan.input_preview,
        "status": scan.status,
        "classification": scan.classification,
        "classification_label": assessment.get(
            "classification_label", CLASSIFICATION_LABELS.get(scan.classification, scan.classification)
        ),
        "risk_score": scan.risk_score,
        "risk_level": scan.risk_level,
        "summary": scan.summary,
        "findings_count": scan.findings_count,
        "is_anonymous": scan.user_id is None,
        "created_at": iso(scan.created_at),
        "completed_at": iso(scan.completed_at),
    }


def scan_full(scan: Scan) -> dict[str, Any]:
    payload = scan_summary(scan)
    payload["analysis"] = scan.analysis or {}
    return payload


def comment_public(comment: Comment) -> dict[str, Any]:
    return {
        "id": comment.id,
        "content": comment.content,
        "status": comment.status,
        "author": {
            "id": comment.author.id,
            "display_name": comment.author.display_name,
        }
        if comment.author
        else {"id": None, "display_name": "Deleted user"},
        "created_at": iso(comment.created_at),
    }


def post_summary(post: CommunityPost, comment_count: int = 0) -> dict[str, Any]:
    linked = None
    if post.scan is not None:
        assessment = (post.scan.analysis or {}).get("assessment") or {}
        linked = {
            "id": post.scan.id,
            "classification": post.scan.classification,
            "classification_label": assessment.get(
                "classification_label",
                CLASSIFICATION_LABELS.get(post.scan.classification, post.scan.classification),
            ),
            "risk_score": post.scan.risk_score,
            "input_type": post.scan.input_type,
        }
    return {
        "id": post.id,
        "title": post.title,
        "content": post.content,
        "url": post.url,
        "status": post.status,
        "verification": "unverified_community_report",
        "author": {
            "id": post.author.id,
            "display_name": post.author.display_name,
        }
        if post.author
        else {"id": None, "display_name": "Deleted user"},
        "linked_scan": linked,
        "comment_count": comment_count,
        "created_at": iso(post.created_at),
        "updated_at": iso(post.updated_at),
    }


def post_detail(post: CommunityPost, comments: list[Comment]) -> dict[str, Any]:
    payload = post_summary(post, comment_count=len(comments))
    payload["comments"] = [comment_public(comment) for comment in comments]
    return payload
