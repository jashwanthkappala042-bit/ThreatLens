import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  CircleAlert,
  Copy,
  Flag,
  LoaderCircle,
  Lock,
  MessageSquare,
  Send,
  ShieldQuestion,
  Trash2,
  UserRound,
} from "lucide-react";
import RiskBadge from "../components/RiskBadge";
import EmptyState from "../components/EmptyState";
import Modal from "../components/Modal";
import ConfirmDialog from "../components/ConfirmDialog";
import { Skeleton } from "../components/Skeleton";
import { api } from "../lib/api";
import { formatDate, relativeTime } from "../lib/format";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";

export default function CommunityPost() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, isAuthenticated, isAdmin } = useAuth();
  const toast = useToast();
  const [post, setPost] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [comment, setComment] = useState("");
  const [commentBusy, setCommentBusy] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [moderating, setModerating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.post(id);
      setPost(data);
    } catch (apiError) {
      setError(apiError);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    window.scrollTo({ top: 0 });
    load();
  }, [load]);

  const addComment = async (event) => {
    event.preventDefault();
    if (!isAuthenticated) {
      navigate("/login", { state: { from: location.pathname } });
      return;
    }
    if (!comment.trim()) return;
    setCommentBusy(true);
    try {
      await api.addComment(post.id, comment.trim());
      setComment("");
      toast.success("Comment added.");
      await load();
    } catch (apiError) {
      toast.error(apiError.message || "The comment could not be added.");
    } finally {
      setCommentBusy(false);
    }
  };

  const removePost = async () => {
    setDeleting(true);
    try {
      await api.deletePost(post.id);
      toast.success("Post deleted.");
      navigate("/community");
    } catch (apiError) {
      toast.error(apiError.message || "The post could not be deleted.");
    } finally {
      setDeleting(false);
    }
  };

  const moderate = async (action) => {
    setModerating(true);
    try {
      await api.moderatePost(post.id, action, action === "remove" ? "Removed from community feed." : "");
      toast.success(action === "remove" ? "Post removed from the feed." : "Post restored.");
      await load();
    } catch (apiError) {
      toast.error(apiError.message || "The moderation action failed.");
    } finally {
      setModerating(false);
    }
  };

  const copyUrl = async () => {
    try {
      await navigator.clipboard.writeText(post.url);
      toast.success("URL copied. Open it only in an isolated environment.");
    } catch {
      toast.error("Could not access the clipboard.");
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-48 rounded-2xl" />
        <Skeleton className="h-32 rounded-2xl" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="panel mx-auto max-w-xl">
        <EmptyState
          icon={CircleAlert}
          title={error.status === 404 ? "Report not found" : "Could not load report"}
          description={
            error.status === 404
              ? "This community report does not exist or was removed."
              : error.message
          }
          action={
            <Link to="/community" className="btn">
              <ArrowLeft size={15} /> Back to feed
            </Link>
          }
        />
      </div>
    );
  }

  const owner = user && post.author?.id === user.id;
  const canModerate = isAdmin && post.status !== "removed";

  return (
    <div className="mx-auto max-w-3xl">
      <Link
        to="/community"
        className="mb-5 inline-flex items-center gap-1.5 text-xs font-semibold text-muted transition hover:text-[var(--text)]"
      >
        <ArrowLeft size={14} /> Community feed
      </Link>

      <article className="panel overflow-hidden">
        <div className="border-b border-[var(--border)] p-5 sm:p-6">
          <div className="flex flex-wrap items-center gap-2">
            <span className="chip border-[color-mix(in_srgb,var(--warn)_30%,transparent)] text-[var(--warn)]">
              <ShieldQuestion size={11} /> Unverified community report
            </span>
            {post.status === "flagged" && (
              <span className="chip border-[color-mix(in_srgb,var(--danger)_30%,transparent)] text-[var(--danger)]">
                Under review · comments closed
              </span>
            )}
            {post.status === "removed" && (
              <span className="chip border-[color-mix(in_srgb,var(--danger)_30%,transparent)] text-[var(--danger)]">
                Removed by moderator
              </span>
            )}
          </div>
          <h1 className="mt-3 break-words text-2xl font-bold leading-tight tracking-tight">{post.title}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-faint">
            <span className="inline-flex items-center gap-1.5">
              <UserRound size={12} /> {post.author?.display_name || "Deleted user"}
            </span>
            <span>{formatDate(post.created_at)}</span>
            <span>{post.comment_count} comments</span>
          </div>
        </div>

        <div className="p-5 sm:p-6">
          <p className="whitespace-pre-wrap text-sm leading-7 text-muted">{post.content}</p>

          {post.url && (
            <div className="mt-5 rounded-xl border border-[color-mix(in_srgb,var(--warn)_28%,transparent)] bg-[color-mix(in_srgb,var(--warn)_5%,transparent)] p-3.5">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--warn)]">
                Shared suspect URL — not opened by ThreatLens
              </p>
              <p className="mono mt-1.5 break-all text-[11px] leading-relaxed">{post.url}</p>
              <div className="mt-2.5 flex flex-wrap gap-2">
                <button type="button" className="btn py-1.5 text-[11px]" onClick={copyUrl}>
                  <Copy size={12} /> Copy URL
                </button>
              </div>
              <p className="mt-2 text-[10px] leading-relaxed text-faint">
                Treat this address as hostile until independently verified. Do not enter credentials or
                payment details on it.
              </p>
            </div>
          )}

          {post.linked_scan && (
            <div className="mt-4 flex flex-wrap items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--panel-soft)] p-3">
              <span className="text-[11px] text-muted">Linked automated scan:</span>
              <RiskBadge classification={post.linked_scan.classification} size="sm" />
              <span className="mono text-[11px] text-faint">
                {post.linked_scan.risk_score}/100 · {post.linked_scan.input_type}
              </span>
              <span className="w-full text-[10px] leading-relaxed text-faint">
                This score comes from the author's saved scan. It has not been independently verified by
                moderators.
              </span>
            </div>
          )}

          <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-[var(--border)] pt-4">
            {isAuthenticated && (
              <button
                type="button"
                className="btn py-2 text-xs"
                onClick={() => setReportOpen(true)}
                disabled={post.status === "removed"}
              >
                <Flag size={13} /> Report
              </button>
            )}
            {(owner || isAdmin) && (
              <button
                type="button"
                className="btn btn-danger py-2 text-xs"
                onClick={() => setDeleteOpen(true)}
              >
                <Trash2 size={13} /> Delete
              </button>
            )}
            {canModerate && (
              <button
                type="button"
                className="btn py-2 text-xs"
                onClick={() => moderate("remove")}
                disabled={moderating}
              >
                {moderating ? <LoaderCircle size={13} className="animate-spin" /> : <Lock size={13} />}
                Remove from feed
              </button>
            )}
            {isAdmin && post.status === "removed" && (
              <button
                type="button"
                className="btn py-2 text-xs"
                onClick={() => moderate("restore")}
                disabled={moderating}
              >
                Restore post
              </button>
            )}
            <span className="ml-auto text-[10px] text-faint">ID {post.id}</span>
          </div>
        </div>
      </article>

      <section className="panel mt-5 overflow-hidden">
        <div className="flex items-center gap-2 border-b border-[var(--border)] px-5 py-3.5">
          <MessageSquare size={16} className="text-[var(--accent)]" />
          <h2 className="text-sm font-semibold">Comments ({post.comments?.length || 0})</h2>
        </div>
        <div className="divide-y divide-[var(--border)]">
          {post.comments?.length ? (
            post.comments.map((item) => (
              <div key={item.id} className="flex gap-3 px-5 py-4">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[var(--accent-soft)] text-[10px] font-bold text-[var(--accent)]">
                  {(item.author?.display_name || "?").slice(0, 1).toUpperCase()}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <p className="text-xs font-semibold">{item.author?.display_name || "Deleted user"}</p>
                    <p className="text-[10px] text-faint">{relativeTime(item.created_at)}</p>
                  </div>
                  <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-muted">
                    {item.content}
                  </p>
                </div>
              </div>
            ))
          ) : (
            <p className="px-5 py-6 text-center text-xs text-faint">No comments yet.</p>
          )}
        </div>
        <div className="border-t border-[var(--border)] p-4">
          {post.status !== "published" ? (
            <p className="flex items-center gap-2 text-xs text-faint">
              <Lock size={14} /> Comments are closed while this report is under moderation.
            </p>
          ) : isAuthenticated ? (
            <form onSubmit={addComment} className="flex flex-col gap-2 sm:flex-row">
              <input
                className="input flex-1"
                placeholder="Add context. Do not share personal data or credentials."
                value={comment}
                maxLength={2000}
                onChange={(event) => setComment(event.target.value)}
                aria-label="Add a comment"
              />
              <button type="submit" className="btn btn-primary py-2.5 text-xs" disabled={commentBusy || !comment.trim()}>
                {commentBusy ? <LoaderCircle size={14} className="animate-spin" /> : <Send size={14} />}
                Comment
              </button>
            </form>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-faint">Sign in to join the discussion.</p>
              <Link
                to="/login"
                state={{ from: location.pathname }}
                className="btn py-2 text-xs"
              >
                Sign in
              </Link>
            </div>
          )}
        </div>
      </section>

      <ReportModal post={post} open={reportOpen} onClose={() => setReportOpen(false)} />
      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onConfirm={removePost}
        busy={deleting}
        title="Delete this report?"
        description="The report and its comments will be permanently deleted. This cannot be undone."
        confirmLabel="Delete report"
      />
    </div>
  );
}

function ReportModal({ post, open, onClose }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const toast = useToast();

  useEffect(() => {
    if (!open) {
      setReason("");
      setError("");
    }
  }, [open]);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { data } = await api.reportPost(post.id, reason);
      toast.success(
        data.post_flagged
          ? "Report received. The post is now flagged for moderation."
          : "Report received. A moderator will review it.",
      );
      onClose();
    } catch (apiError) {
      setError(apiError.message || "The report could not be submitted.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Report this community post"
      description="Reports are reviewed by moderators. Repeated open reports can flag a post automatically."
      footer={
        <>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" form="report-form" className="btn btn-danger" disabled={busy}>
            {busy ? <LoaderCircle size={15} className="animate-spin" /> : <Flag size={15} />}
            {busy ? "Submitting…" : "Submit report"}
          </button>
        </>
      }
    >
      <form id="report-form" onSubmit={submit} className="space-y-3">
        <label className="label" htmlFor="report-reason">
          Why should this be reviewed?
        </label>
        <textarea
          id="report-reason"
          className="input min-h-[110px] resize-y"
          placeholder="Describe the problem, for example: contains personal information, targets a real person, or shares a link without context."
          minLength={5}
          maxLength={500}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          required
        />
        {error && <p className="text-xs text-[var(--danger)]">{error}</p>}
      </form>
    </Modal>
  );
}
