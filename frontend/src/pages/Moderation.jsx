import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  Check,
  CircleAlert,
  Flag,
  LoaderCircle,
  ShieldCheck,
  ShieldOff,
  Trash2,
} from "lucide-react";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import ConfirmDialog from "../components/ConfirmDialog";
import { Skeleton } from "../components/Skeleton";
import { api } from "../lib/api";
import { relativeTime } from "../lib/format";
import { useToast } from "../context/ToastContext";

export default function Moderation() {
  const toast = useToast();
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [working, setWorking] = useState("");
  const [removeTarget, setRemoveTarget] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.moderationReports();
      setReports(data || []);
    } catch (apiError) {
      setError(apiError.message || "The moderation queue could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const resolve = async (report, action) => {
    setWorking(`report-${report.id}`);
    try {
      await api.resolveReport(report.id, action, action === "resolve" ? "Reviewed." : "No action needed.");
      toast.success(action === "resolve" ? "Report resolved." : "Report dismissed.");
      await load();
    } catch (apiError) {
      toast.error(apiError.message || "The report could not be updated.");
    } finally {
      setWorking("");
    }
  };

  const removePost = async () => {
    if (!removeTarget) return;
    setWorking(`post-${removeTarget.post.id}`);
    try {
      await api.moderatePost(removeTarget.post.id, "remove", "Removed from moderation queue.");
      toast.success("Post removed and open reports resolved.");
      setRemoveTarget(null);
      await load();
    } catch (apiError) {
      toast.error(apiError.message || "The post could not be removed.");
    } finally {
      setWorking("");
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Administration"
        title="Moderation queue"
        description="Open community reports, newest first. Moderation actions are recorded in the audit log. Content stays labelled unverified."
        actions={
          <button type="button" className="btn py-2 text-xs" onClick={load} disabled={loading}>
            {loading ? <LoaderCircle size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
            Refresh queue
          </button>
        }
      />

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-32 rounded-2xl" />
          ))}
        </div>
      ) : error ? (
        <div className="panel">
          <EmptyState
            icon={CircleAlert}
            title="Queue unavailable"
            description={error}
            action={
              <button type="button" className="btn" onClick={load}>
                Retry
              </button>
            }
          />
        </div>
      ) : reports.length === 0 ? (
        <div className="panel">
          <EmptyState
            icon={ShieldCheck}
            title="No open reports"
            description="There are no community reports waiting for review. This queue does not include content that has not been reported."
          />
        </div>
      ) : (
        <div className="space-y-3">
          {reports.map((report) => {
            const busy = working === `report-${report.id}` || working === `post-${report.post?.id}`;
            return (
              <article key={report.id} className="panel p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="chip border-[color-mix(in_srgb,var(--danger)_30%,transparent)] text-[var(--danger)]">
                        <Flag size={11} /> Report #{report.id}
                      </span>
                      <span className="text-[10px] text-faint">{relativeTime(report.created_at)}</span>
                      {report.post?.status === "flagged" && (
                        <span className="chip text-[var(--warn)]">Post flagged</span>
                      )}
                    </div>
                    <p className="mt-2 text-sm leading-relaxed">{report.reason}</p>
                    <p className="mt-2 text-[11px] text-faint">
                      Reported by {report.reporter?.display_name || "deleted user"} · post by{" "}
                      {report.post?.author || "deleted user"}
                    </p>
                  </div>
                  {report.post && (
                    <Link
                      to={`/community/${report.post.id}`}
                      className="btn py-1.5 text-[11px]"
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open post <ArrowUpRight size={12} />
                    </Link>
                  )}
                </div>

                {report.post && (
                  <div className="mt-3 rounded-xl border border-[var(--border)] bg-[var(--panel-soft)] p-3">
                    <p className="text-xs font-semibold">{report.post.title}</p>
                    <p className="mt-1 text-[10px] text-faint">Post ID {report.post.id}</p>
                  </div>
                )}

                <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[var(--border)] pt-3">
                  <button
                    type="button"
                    className="btn py-1.5 text-[11px]"
                    onClick={() => resolve(report, "resolve")}
                    disabled={busy}
                  >
                    {working === `report-${report.id}` ? (
                      <LoaderCircle size={12} className="animate-spin" />
                    ) : (
                      <Check size={12} />
                    )}
                    Resolve
                  </button>
                  <button
                    type="button"
                    className="btn py-1.5 text-[11px]"
                    onClick={() => resolve(report, "dismiss")}
                    disabled={busy}
                  >
                    <ShieldOff size={12} /> Dismiss
                  </button>
                  {report.post && (
                    <button
                      type="button"
                      className="btn btn-danger ml-auto py-1.5 text-[11px]"
                      onClick={() => setRemoveTarget(report)}
                      disabled={busy}
                    >
                      <Trash2 size={12} /> Remove post
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        open={Boolean(removeTarget)}
        onClose={() => setRemoveTarget(null)}
        onConfirm={removePost}
        busy={working.startsWith("post-")}
        title="Remove this post?"
        description={
          removeTarget
            ? `“${removeTarget.post?.title}” will be hidden from the feed and all open reports for it will be resolved.`
            : ""
        }
        confirmLabel="Remove post"
      />
    </div>
  );
}
