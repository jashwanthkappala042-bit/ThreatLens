import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  CircleAlert,
  Clock3,
  LoaderCircle,
  MessageSquare,
  Plus,
  Search,
  ShieldQuestion,
  Users,
} from "lucide-react";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import Modal from "../components/Modal";
import RiskBadge from "../components/RiskBadge";
import { Skeleton } from "../components/Skeleton";
import { api } from "../lib/api";
import { relativeTime, titleCase } from "../lib/format";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";

function PostCard({ post }) {
  return (
    <Link
      to={`/community/${post.id}`}
      className="panel group flex flex-col p-5 transition hover:border-[var(--border-strong)] hover:shadow-glow"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="chip border-[color-mix(in_srgb,var(--warn)_30%,transparent)] text-[var(--warn)]">
          <ShieldQuestion size={11} /> Unverified
        </span>
        {post.status === "flagged" && (
          <span className="chip border-[color-mix(in_srgb,var(--danger)_30%,transparent)] text-[var(--danger)]">
            Under review
          </span>
        )}
        {post.linked_scan && (
          <span className="chip">
            Linked scan · {post.linked_scan.risk_score}/100
          </span>
        )}
      </div>
      <h3 className="mt-3 line-clamp-2 text-base font-semibold leading-snug transition group-hover:text-[var(--accent)]">
        {post.title}
      </h3>
      <p className="mt-2 line-clamp-3 flex-1 text-xs leading-relaxed text-muted">{post.content}</p>
      {post.url && (
        <p className="mono mt-3 truncate text-[10px] text-faint" title={post.url}>
          {post.url}
        </p>
      )}
      <div className="mt-4 flex items-center justify-between gap-2 border-t border-[var(--border)] pt-3 text-[10px] text-faint">
        <span className="inline-flex items-center gap-1.5">
          <span className="grid h-5 w-5 place-items-center rounded-md bg-[var(--accent-soft)] text-[8px] font-bold text-[var(--accent)]">
            {(post.author?.display_name || "?").slice(0, 1).toUpperCase()}
          </span>
          {post.author?.display_name || "Deleted user"}
        </span>
        <span className="inline-flex items-center gap-3">
          <span className="inline-flex items-center gap-1">
            <MessageSquare size={11} /> {post.comment_count}
          </span>
          <span className="inline-flex items-center gap-1">
            <Clock3 size={11} /> {relativeTime(post.created_at)}
          </span>
        </span>
      </div>
    </Link>
  );
}

export default function Community() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const [posts, setPosts] = useState([]);
  const [meta, setMeta] = useState({ page: 1, pages: 1, total: 0, verification_note: "" });
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setSearch(query.trim());
      setPage(1);
    }, 350);
    return () => window.clearTimeout(handle);
  }, [query]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await api.posts({ page, per_page: 9, q: search });
      setPosts(result.data || []);
      setMeta(result.meta || { page: 1, pages: 1, total: 0 });
    } catch (apiError) {
      setError(apiError.message || "The community feed could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [page, search]);

  useEffect(() => {
    load();
  }, [load]);

  const openComposer = () => {
    if (!isAuthenticated) {
      toast.info("Sign in to publish a community report.");
      navigate("/login", { state: { from: location.pathname } });
      return;
    }
    setOpen(true);
  };

  return (
    <div>
      <PageHeader
        eyebrow="Community"
        title="Unverified reports"
        description="Reports shared by other users. Nothing here is confirmed until it has been independently analysed — treat every link as hostile."
        actions={
          <button type="button" className="btn btn-primary py-2 text-xs" onClick={openComposer}>
            <Plus size={15} /> Publish a report
          </button>
        }
      />

      <div className="mb-4 flex flex-col gap-2 rounded-xl border border-[color-mix(in_srgb,var(--warn)_26%,transparent)] bg-[color-mix(in_srgb,var(--warn)_6%,transparent)] px-4 py-3 text-[11px] leading-relaxed text-[var(--warn)] sm:flex-row sm:items-center sm:justify-between">
        <span className="inline-flex items-start gap-2">
          <CircleAlert size={14} className="mt-0.5 shrink-0" />
          Community content is unverified. A report is not a ThreatLens verdict, and links are not opened
          automatically.
        </span>
        <span className="shrink-0 text-[10px] uppercase tracking-wider text-faint">
          {meta.total || 0} reports
        </span>
      </div>

      <div className="panel mb-4 flex flex-col gap-2 p-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search
            size={15}
            className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-faint"
          />
          <input
            className="input py-2.5 pl-10"
            placeholder="Search titles and descriptions…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="Search community reports"
          />
        </div>
        <span className="px-1 text-[11px] text-faint">
          Page {meta.page} of {meta.pages}
        </span>
      </div>

      {loading ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-56 rounded-2xl" />
          ))}
        </div>
      ) : error ? (
        <div className="panel">
          <EmptyState
            icon={CircleAlert}
            title="Could not load the feed"
            description={error}
            action={
              <button type="button" className="btn" onClick={load}>
                Retry
              </button>
            }
          />
        </div>
      ) : posts.length === 0 ? (
        <div className="panel">
          <EmptyState
            icon={Users}
            title={search ? "No reports match that search" : "The feed is empty"}
            description={
              search
                ? "Try a different term, or clear the search."
                : "No community reports have been published yet. A report can describe a suspicious message or link for others to review."
            }
            action={
              <button type="button" className="btn btn-primary" onClick={openComposer}>
                <Plus size={16} /> Publish the first report
              </button>
            }
          />
        </div>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {posts.map((post) => (
              <PostCard key={post.id} post={post} />
            ))}
          </div>
          {(meta.pages > 1 || page > 1) && (
            <div className="mt-4 flex items-center justify-center gap-2">
              <button
                type="button"
                className="btn py-2 text-xs"
                disabled={page <= 1}
                onClick={() => setPage((current) => current - 1)}
              >
                Previous
              </button>
              <span className="px-2 text-[11px] text-faint">
                {page} / {meta.pages}
              </span>
              <button
                type="button"
                className="btn py-2 text-xs"
                disabled={page >= meta.pages}
                onClick={() => setPage((current) => current + 1)}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}

      <Composer open={open} onClose={() => setOpen(false)} onCreated={load} />
    </div>
  );
}

function Composer({ open, onClose, onCreated }) {
  const { isAuthenticated, user } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [form, setForm] = useState({ title: "", content: "", url: "", scan_id: "" });
  const [scans, setScans] = useState([]);
  const [scansLoading, setScansLoading] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !isAuthenticated) return;
    let active = true;
    setScansLoading(true);
    api
      .history({ per_page: 10 })
      .then(({ data }) => {
        if (active) setScans(data || []);
      })
      .catch(() => {
        if (active) setScans([]);
      })
      .finally(() => {
        if (active) setScansLoading(false);
      });
    return () => {
      active = false;
    };
  }, [open, isAuthenticated]);

  useEffect(() => {
    if (!open) {
      setForm({ title: "", content: "", url: "", scan_id: "" });
      setError("");
    }
  }, [open]);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { data } = await api.createPost({
        title: form.title,
        content: form.content,
        url: form.url,
        scan_id: form.scan_id || undefined,
      });
      toast.success("Report published as unverified community content.");
      onClose();
      onCreated?.();
      navigate(`/community/${data.id}`);
    } catch (apiError) {
      setError(apiError.message || "The report could not be published.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Publish an unverified report"
      description={
        user
          ? `Publishing as ${user.display_name}. Do not include personal data, credentials or private message contents you are not authorised to share.`
          : "Sign in to publish."
      }
      footer={
        <>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" form="community-form" className="btn btn-primary" disabled={busy}>
            {busy ? <LoaderCircle size={15} className="animate-spin" /> : <Plus size={15} />}
            {busy ? "Publishing…" : "Publish report"}
          </button>
        </>
      }
    >
      <form id="community-form" onSubmit={submit} className="space-y-4">
        <div>
          <label className="label" htmlFor="post-title">
            Title
          </label>
          <input
            id="post-title"
            className="input"
            placeholder="Fake delivery message with a shortened link"
            minLength={5}
            maxLength={160}
            value={form.title}
            onChange={(event) => setForm({ ...form, title: event.target.value })}
            required
          />
        </div>
        <div>
          <label className="label" htmlFor="post-content">
            Description
          </label>
          <textarea
            id="post-content"
            className="input min-h-[150px] resize-y"
            placeholder="Describe what you observed without including passwords, OTPs, account numbers or other sensitive details."
            minLength={10}
            maxLength={5000}
            value={form.content}
            onChange={(event) => setForm({ ...form, content: event.target.value })}
            required
          />
        </div>
        <div>
          <label className="label" htmlFor="post-url">
            Suspect URL <span className="font-normal normal-case tracking-normal">(optional)</span>
          </label>
          <input
            id="post-url"
            className="input mono text-xs"
            placeholder="https://example.com/link"
            value={form.url}
            maxLength={2048}
            onChange={(event) => setForm({ ...form, url: event.target.value })}
          />
          <p className="mt-1 text-[10px] text-faint">
            The URL is validated and displayed as text. ThreatLens does not fetch it when rendering the
            feed.
          </p>
        </div>
        <div>
          <label className="label" htmlFor="post-scan">
            Link a saved scan <span className="font-normal normal-case tracking-normal">(optional)</span>
          </label>
          <select
            id="post-scan"
            className="input text-sm"
            value={form.scan_id}
            onChange={(event) => setForm({ ...form, scan_id: event.target.value })}
            disabled={scansLoading}
          >
            <option value="">No linked scan</option>
            {scans.map((scan) => (
              <option key={scan.id} value={scan.id}>
                {titleCase(scan.input_type)} · {scan.input_label.slice(0, 70)} ({scan.risk_score}/100)
              </option>
            ))}
          </select>
          <p className="mt-1 text-[10px] text-faint">
            Only scans saved to your own account can be linked. The linked risk score is shown with a
            reminder that community content is unverified.
          </p>
        </div>
        {error && (
          <p className="rounded-lg border border-[color-mix(in_srgb,var(--danger)_30%,transparent)] bg-[color-mix(in_srgb,var(--danger)_8%,transparent)] p-2.5 text-xs text-[var(--danger)]">
            {error}
          </p>
        )}
        <div className="flex items-start gap-2 rounded-lg bg-[var(--panel-soft)] p-2.5 text-[10px] leading-relaxed text-faint">
          <ShieldQuestion size={13} className="mt-0.5 shrink-0 text-[var(--warn)]" />
          Your report will be published immediately and marked unverified. Other users can report it for
          moderation.
        </div>
      </form>
    </Modal>
  );
}
