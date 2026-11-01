"""Database-driven dashboard statistics."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from flask import Blueprint
from sqlalchemy import func, select

from ..database import get_session
from ..models import Comment, CommunityPost, Scan, ScanFinding, utcnow
from ..responses import success
from ..security import get_current_user
from ..serializers import post_summary, scan_summary

bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


@bp.get("/stats")
def stats():
    user = get_current_user()
    session = get_session()
    base = Scan.user_id == user.id

    total = session.scalar(select(func.count()).select_from(Scan).where(base)) or 0
    rows = session.execute(
        select(Scan.classification, func.count()).where(base).group_by(Scan.classification)
    ).all()
    counts = {classification: count for classification, count in rows}
    last_week_start = utcnow() - timedelta(days=7)
    last_week = (
        session.scalar(
            select(func.count()).select_from(Scan).where(base, Scan.created_at >= last_week_start)
        )
        or 0
    )
    average = session.scalar(select(func.avg(Scan.risk_score)).where(base)) or 0
    medium_or_worse = (
        session.scalar(
            select(func.count()).select_from(Scan).where(
                base, Scan.classification.in_(["suspicious", "malicious"])
            )
        )
        or 0
    )

    return success(
        {
            "total_scans": total,
            "counts": {
                "no_significant_indicators": counts.get("no_significant_indicators", 0),
                "suspicious": counts.get("suspicious", 0),
                "malicious": counts.get("malicious", 0),
                "unknown": counts.get("unknown", 0),
            },
            "scans_last_7_days": last_week,
            "flagged_scans": medium_or_worse,
            "average_risk_score": round(float(average), 1),
        }
    )


@bp.get("/activity")
def activity():
    user = get_current_user()
    session = get_session()
    start = (utcnow() - timedelta(days=13)).replace(hour=0, minute=0, second=0, microsecond=0)
    scans = session.scalars(
        select(Scan).where(Scan.user_id == user.id, Scan.created_at >= start)
    ).all()
    counts = Counter(scan.created_at.date() for scan in scans if scan.created_at)
    days = []
    for offset in range(13, -1, -1):
        day = (utcnow() - timedelta(days=offset)).date()
        days.append({"date": day.isoformat(), "count": counts.get(day, 0)})
    return success({"days": days, "range_days": 14})


@bp.get("/categories")
def categories():
    user = get_current_user()
    session = get_session()
    rows = session.execute(
        select(ScanFinding.category, func.count(ScanFinding.id))
        .join(Scan, Scan.id == ScanFinding.scan_id)
        .where(
            Scan.user_id == user.id,
            ScanFinding.severity.in_(["medium", "high", "critical"]),
        )
        .group_by(ScanFinding.category)
        .order_by(func.count(ScanFinding.id).desc())
        .limit(8)
    ).all()
    return success([{"category": category, "count": count} for category, count in rows])


@bp.get("/overview")
def overview():
    user = get_current_user()
    session = get_session()

    recent = list(
        session.scalars(
            select(Scan)
            .where(Scan.user_id == user.id)
            .order_by(Scan.created_at.desc())
            .limit(5)
        )
    )
    posts = list(
        session.scalars(
            select(CommunityPost)
            .where(CommunityPost.status.in_(["published", "flagged"]))
            .order_by(CommunityPost.created_at.desc())
            .limit(3)
        )
    )
    comment_counts = {}
    if posts:
        rows = session.execute(
            select(Comment.post_id, func.count(Comment.id))
            .where(Comment.post_id.in_([post.id for post in posts]), Comment.status == "published")
            .group_by(Comment.post_id)
        ).all()
        comment_counts = {post_id: count for post_id, count in rows}

    return success(
        {
            "recent_scans": [scan_summary(scan) for scan in recent],
            "community_posts": [post_summary(post, comment_counts.get(post.id, 0)) for post in posts],
        }
    )
