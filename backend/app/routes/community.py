"""Community posts, comments, reports and moderation."""

from __future__ import annotations

from flask import Blueprint, current_app, request
from sqlalchemy import func, select

from ..database import get_session
from ..models import Comment, CommunityPost, CommunityReport, Scan, utcnow
from ..responses import ApiError, success
from ..security import audit, get_current_user, rate_limit, require_admin
from ..serializers import comment_public, post_detail, post_summary
from ..utils.url_safety import InvalidTarget, validate_url

bp = Blueprint("community", __name__, url_prefix="/api/community")


def _text(payload: dict, field: str, *, minimum: int, maximum: int, label: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise ApiError("invalid_request", f"{label} is required.", 422)
    value = value.strip()
    if len(value) < minimum:
        raise ApiError("invalid_request", f"{label} must be at least {minimum} characters.", 422)
    if len(value) > maximum:
        raise ApiError("invalid_request", f"{label} must be {maximum} characters or fewer.", 422)
    if "\x00" in value:
        raise ApiError("invalid_request", f"{label} contains unsupported characters.", 422)
    return value


def _comment_counts(post_ids: list[int]) -> dict[int, int]:
    if not post_ids:
        return {}
    session = get_session()
    rows = session.execute(
        select(Comment.post_id, func.count(Comment.id))
        .where(Comment.post_id.in_(post_ids), Comment.status == "published")
        .group_by(Comment.post_id)
    ).all()
    return {post_id: count for post_id, count in rows}


def _get_post(post_id: int) -> CommunityPost:
    post = get_session().get(CommunityPost, post_id)
    if post is None:
        raise ApiError("post_not_found", "That community post does not exist.", 404)
    return post


@bp.get("/posts")
def list_posts():
    page = max(1, request.args.get("page", default=1, type=int) or 1)
    per_page = min(50, max(1, request.args.get("per_page", default=10, type=int) or 10))
    search = request.args.get("q", "").strip()

    filters = [CommunityPost.status.in_(["published", "flagged"])]
    if search:
        term = f"%{search[:100]}%"
        filters.append(CommunityPost.title.ilike(term) | CommunityPost.content.ilike(term))

    session = get_session()
    total = session.scalar(
        select(func.count()).select_from(CommunityPost).where(*filters)
    ) or 0
    posts = list(
        session.scalars(
            select(CommunityPost)
            .where(*filters)
            .order_by(CommunityPost.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    )
    counts = _comment_counts([post.id for post in posts])
    return success(
        [post_summary(post, counts.get(post.id, 0)) for post in posts],
        meta={
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": max(1, (total + per_page - 1) // per_page),
            "verification_note": "Community reports are unverified until independently analyzed.",
        },
    )


@bp.post("/posts")
@rate_limit("community")
def create_post():
    user = get_current_user()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError("invalid_request", "Send a JSON object.", 400)
    title = _text(payload, "title", minimum=5, maximum=160, label="Title")
    content = _text(payload, "content", minimum=10, maximum=5000, label="Description")

    raw_url = payload.get("url") or ""
    url = ""
    if raw_url:
        if not isinstance(raw_url, str):
            raise ApiError("invalid_url", "URL must be text.", 422)
        try:
            url = validate_url(raw_url.strip(), resolve=False).normalized_url
        except InvalidTarget as exc:
            raise ApiError(exc.code, exc.message, 422)

    scan_id = payload.get("scan_id")
    scan = None
    if scan_id:
        if not isinstance(scan_id, str):
            raise ApiError("invalid_scan", "Scan reference is invalid.", 422)
        scan = get_session().get(Scan, scan_id)
        if scan is None:
            raise ApiError("scan_not_found", "The linked scan does not exist.", 404)
        if scan.user_id != user.id:
            raise ApiError(
                "forbidden",
                "You can only link scans saved to your own account. Anonymous scans cannot be linked.",
                403,
            )

    post = CommunityPost(
        user_id=user.id,
        scan_id=scan.id if scan else None,
        title=title,
        content=content,
        url=url,
        status="published",
        created_at=utcnow(),
    )
    session = get_session()
    session.add(post)
    session.commit()
    audit("community.post.created", detail=f"post={post.id}", user_id=user.id)
    return success(post_summary(post, 0), status=201)


@bp.get("/posts/<int:post_id>")
def get_post(post_id: int):
    user = get_current_user(optional=True)
    post = _get_post(post_id)
    if post.status == "removed" and not (user and user.is_admin):
        raise ApiError("post_not_found", "That community post does not exist.", 404)
    session = get_session()
    comments = list(
        session.scalars(
            select(Comment)
            .where(Comment.post_id == post.id, Comment.status == "published")
            .order_by(Comment.created_at.asc())
        )
    )
    payload = post_detail(post, comments)
    if user and user.is_admin:
        payload["moderation"] = {
            "report_count": session.scalar(
                select(func.count()).select_from(CommunityReport).where(
                    CommunityReport.post_id == post.id, CommunityReport.status == "open"
                )
            )
            or 0
        }
    return success(payload)


@bp.post("/posts/<int:post_id>/comments")
@rate_limit("community")
def add_comment(post_id: int):
    user = get_current_user()
    post = _get_post(post_id)
    if post.status != "published":
        raise ApiError(
            "post_unavailable",
            "Comments are closed on this post while it is under moderation.",
            409,
        )
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError("invalid_request", "Send a JSON object.", 400)
    content = _text(payload, "content", minimum=1, maximum=2000, label="Comment")
    comment = Comment(
        post_id=post.id,
        user_id=user.id,
        content=content,
        status="published",
        created_at=utcnow(),
    )
    session = get_session()
    session.add(comment)
    session.commit()
    audit("community.comment.created", detail=f"post={post.id} comment={comment.id}", user_id=user.id)
    return success(comment_public(comment), status=201)


@bp.post("/posts/<int:post_id>/report")
@rate_limit("community")
def report_post(post_id: int):
    user = get_current_user()
    post = _get_post(post_id)
    if post.status == "removed":
        raise ApiError("post_not_found", "That community post does not exist.", 404)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError("invalid_request", "Send a JSON object.", 400)
    reason = _text(payload, "reason", minimum=5, maximum=500, label="Report reason")

    session = get_session()
    existing = session.scalar(
        select(CommunityReport).where(
            CommunityReport.post_id == post.id,
            CommunityReport.reporter_id == user.id,
            CommunityReport.status == "open",
        )
    )
    if existing is not None:
        raise ApiError(
            "already_reported",
            "You already have an open report for this post.",
            409,
        )
    report = CommunityReport(
        post_id=post.id,
        reporter_id=user.id,
        reason=reason,
        status="open",
        created_at=utcnow(),
    )
    session.add(report)
    session.flush()
    open_reports = session.scalar(
        select(func.count()).select_from(CommunityReport).where(
            CommunityReport.post_id == post.id, CommunityReport.status == "open"
        )
    ) or 0
    flagged = False
    threshold = int(current_app.config.get("REPORTS_TO_FLAG", 3))
    if open_reports >= threshold and post.status == "published":
        post.status = "flagged"
        flagged = True
    session.commit()
    audit("community.post.reported", detail=f"post={post.id} report={report.id}", user_id=user.id)
    return success(
        {
            "report_id": report.id,
            "post_flagged": flagged,
            "message": "Report received. Community content remains unverified until moderated.",
        },
        status=201,
    )


@bp.delete("/posts/<int:post_id>")
def delete_post(post_id: int):
    user = get_current_user()
    post = _get_post(post_id)
    if post.user_id != user.id and not user.is_admin:
        raise ApiError("forbidden", "You can only delete your own posts.", 403)
    session = get_session()
    session.delete(post)
    session.commit()
    audit("community.post.deleted", detail=f"post={post_id}", user_id=user.id)
    return success({"deleted": post_id}, message="Post deleted.")


@bp.get("/moderation/reports")
def moderation_reports():
    user = get_current_user()
    require_admin(user)
    session = get_session()
    reports = list(
        session.scalars(
            select(CommunityReport)
            .where(CommunityReport.status == "open")
            .order_by(CommunityReport.created_at.asc())
            .limit(100)
        )
    )
    return success(
        [
            {
                "id": report.id,
                "reason": report.reason,
                "status": report.status,
                "created_at": report.created_at.isoformat() if report.created_at else None,
                "reporter": {
                    "id": report.reporter.id,
                    "display_name": report.reporter.display_name,
                }
                if report.reporter
                else None,
                "post": {
                    "id": report.post.id,
                    "title": report.post.title,
                    "status": report.post.status,
                    "author": report.post.author.display_name if report.post.author else "Deleted user",
                }
                if report.post
                else None,
            }
            for report in reports
        ]
    )


@bp.patch("/posts/<int:post_id>/moderation")
def moderate_post(post_id: int):
    user = get_current_user()
    require_admin(user)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError("invalid_request", "Send a JSON object.", 400)
    action = payload.get("action")
    if action not in {"remove", "restore"}:
        raise ApiError("invalid_action", "Action must be 'remove' or 'restore'.", 422)
    note = str(payload.get("note", "") or "")[:500]
    post = _get_post(post_id)
    session = get_session()
    post.status = "removed" if action == "remove" else "published"
    if action == "remove":
        for report in session.scalars(
            select(CommunityReport).where(
                CommunityReport.post_id == post.id, CommunityReport.status == "open"
            )
        ):
            report.status = "resolved"
            report.resolved_at = utcnow()
            report.resolution_note = note or "Post removed by moderator."
    session.commit()
    audit("community.post.moderated", detail=f"post={post.id} action={action}", user_id=user.id)
    return success({"post_id": post.id, "status": post.status}, message="Moderation action applied.")


@bp.patch("/reports/<int:report_id>")
def resolve_report(report_id: int):
    user = get_current_user()
    require_admin(user)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError("invalid_request", "Send a JSON object.", 400)
    action = payload.get("action")
    if action not in {"resolve", "dismiss"}:
        raise ApiError("invalid_action", "Action must be 'resolve' or 'dismiss'.", 422)
    note = str(payload.get("note", "") or "")[:500]
    session = get_session()
    report = session.get(CommunityReport, report_id)
    if report is None:
        raise ApiError("report_not_found", "That report does not exist.", 404)
    report.status = "resolved" if action == "resolve" else "dismissed"
    report.resolved_at = utcnow()
    report.resolution_note = note
    session.commit()
    audit("community.report.moderated", detail=f"report={report.id} action={action}", user_id=user.id)
    return success({"report_id": report.id, "status": report.status})
