import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowUpRight,
  Check,
  ChevronDown,
  CircleAlert,
  Copy,
  Download,
  FileText,
  Filter,
  Gauge,
  Layers3,
  Lightbulb,
  Link2,
  ListChecks,
  LoaderCircle,
  ScanSearch,
  Share2,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import PageHeader from "../components/PageHeader";
import RiskBadge from "../components/RiskBadge";
import ScoreGauge from "../components/ScoreGauge";
import EmptyState from "../components/EmptyState";
import Modal from "../components/Modal";
import ScanEvidence, { StageStatus } from "../components/ScanEvidence";
import { Skeleton } from "../components/Skeleton";
import { api, downloadAuthenticated, getToken } from "../lib/api";
import { classificationMeta, formatDate, inputTypeLabel, severityMeta, titleCase } from "../lib/format";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "findings", label: "Findings" },
  { id: "evidence", label: "Evidence" },
  { id: "reasoning", label: "Decision trace" },
  { id: "limitations", label: "Limitations" },
];

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const toast = useToast();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      toast.success("Link copied.");
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error("Could not access the clipboard.");
    }
  };
  return (
    <button type="button" className="btn py-2 text-xs" onClick={copy}>
      {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "Copied" : "Copy link"}
    </button>
  );
}

function VerdictHeader({ scan }) {
  const assessment = scan.analysis?.assessment || {};
  const meta = classificationMeta(scan.classification);
  return (
    <div className="panel overflow-hidden">
      <div className="grid gap-0 md:grid-cols-[210px_minmax(0,1fr)]">
        <div className="flex items-center justify-center border-b border-[var(--border)] p-5 md:border-b-0 md:border-r">
          <ScoreGauge score={scan.risk_score} classification={scan.classification} size={190} />
        </div>
        <div className="p-5 sm:p-6">
          <div className="flex flex-wrap items-center gap-2">
            <RiskBadge classification={scan.classification} />
            <span className="chip">
              {inputTypeLabel(scan.input_type)} · {scan.is_anonymous ? "Anonymous" : "Saved to account"}
            </span>
            <span className="chip">Heuristic, uncalibrated</span>
          </div>
          <h2 className="mt-3 break-words text-lg font-bold leading-snug sm:text-xl">
            {scan.input_label}
          </h2>
          {scan.input_preview && (
            <p className="mt-1 break-words text-xs leading-relaxed text-muted">{scan.input_preview}</p>
          )}
          <p className="mt-3 text-sm leading-relaxed text-muted">{scan.summary || meta.description}</p>
          <div className="mt-4 grid gap-3 border-t border-[var(--border)] pt-4 text-xs sm:grid-cols-3">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-faint">Confidence</p>
              <p className="mt-1 font-semibold capitalize">{assessment.confidence?.level || "low"}</p>
              <p className="mt-0.5 text-[10px] leading-relaxed text-faint">
                Based on category coverage and completed stages, not statistics.
              </p>
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-faint">Indicators</p>
              <p className="mt-1 font-semibold">{scan.findings_count ?? assessment.supporting_findings?.length ?? 0}</p>
              <p className="mt-0.5 text-[10px] leading-relaxed text-faint">
                {assessment.categories?.length || 0} indicator categories
              </p>
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-faint">Completed</p>
              <p className="mt-1 font-semibold">{formatDate(scan.completed_at || scan.created_at)}</p>
              <p className="mt-0.5 text-[10px] leading-relaxed text-faint">
                {assessment.evidence_quality?.completed || 0} of{" "}
                {assessment.evidence_quality?.attempted || 0} attempted stages
              </p>
            </div>
          </div>
        </div>
      </div>
      {scan.classification === "unknown" && (
        <div className="flex items-start gap-2.5 border-t border-[color-mix(in_srgb,var(--warn)_30%,transparent)] bg-[color-mix(in_srgb,var(--warn)_7%,transparent)] px-5 py-3 text-xs leading-relaxed text-[var(--warn)]">
          <CircleAlert size={16} className="mt-0.5 shrink-0" />
          <span>
            Inconclusive is not safe. Essential evidence was missing or could not be assessed. Review the
            limitations before trusting this content.
          </span>
        </div>
      )}
    </div>
  );
}

function CategoryBars({ categories }) {
  if (!categories?.length) {
    return <p className="text-xs text-faint">No category contributions were scored.</p>;
  }
  const max = Math.max(...categories.map((item) => item.score), 1);
  return (
    <div className="space-y-3">
      {categories.map((category) => (
        <div key={category.category}>
          <div className="flex items-baseline justify-between gap-3 text-xs">
            <span className="font-medium">{titleCase(category.category)}</span>
            <span className="mono text-faint">{category.score.toFixed(1)}</span>
          </div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[var(--panel-soft)]">
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.max(4, (category.score / max) * 100)}%`,
                background: "linear-gradient(90deg, var(--accent), color-mix(in srgb, var(--accent) 55%, var(--warn)))",
              }}
            />
          </div>
          <p className="mt-1 truncate text-[10px] text-faint">
            {category.indicator_count} indicator{category.indicator_count === 1 ? "" : "s"}:{" "}
            {category.indicators?.join(", ")}
          </p>
        </div>
      ))}
    </div>
  );
}

function FindingCard({ finding, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const severity = severityMeta(finding.severity);
  return (
    <article
      className="rounded-xl border border-[var(--border)] bg-[var(--panel-soft)] transition hover:border-[var(--border-strong)]"
      style={{ borderLeft: `3px solid ${severity.color}` }}
    >
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-start gap-3 p-4 text-left"
        aria-expanded={open}
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.1em]"
              style={{
                color: severity.color,
                background: `color-mix(in srgb, ${severity.color} 10%, transparent)`,
              }}
            >
              {severity.label}
            </span>
            <span className="text-[10px] uppercase tracking-wider text-faint">
              {titleCase(finding.category)} · {finding.source}
            </span>
            {typeof finding.weight === "number" && (
              <span className="mono ml-auto text-[10px] text-faint">weight {finding.weight}</span>
            )}
          </div>
          <h4 className="mt-2 text-sm font-semibold leading-snug">{finding.title}</h4>
          <p className={`mt-1 text-xs leading-relaxed text-muted ${open ? "" : "line-clamp-2"}`}>
            {finding.description}
          </p>
        </div>
        <ChevronDown
          size={16}
          className={`mt-1 shrink-0 text-faint transition ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div className="border-t border-[var(--border)] px-4 py-3">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-faint">
            Evidence attached to this indicator
          </p>
          <pre className="mono max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-[var(--bg-elevated)] p-3 text-[10px] leading-relaxed text-muted">
            {JSON.stringify(finding.evidence || {}, null, 2)}
          </pre>
          <p className="mt-2 text-[10px] text-faint">
            Indicator ID: <span className="mono">{finding.indicator_id || "—"}</span>
          </p>
        </div>
      )}
    </article>
  );
}

function Overview({ scan, onShare }) {
  const assessment = scan.analysis?.assessment || {};
  const findings = assessment.supporting_findings || [];
  const top = findings.slice(0, 3);
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(280px,0.75fr)]">
      <div className="space-y-4">
        <section className="panel p-5">
          <div className="flex items-center gap-2">
            <ListChecks size={16} className="text-[var(--accent)]" />
            <h3 className="text-sm font-semibold">Recommended actions</h3>
          </div>
          {assessment.recommended_actions?.length ? (
            <ul className="mt-3 space-y-2.5">
              {assessment.recommended_actions.map((action) => (
                <li key={action} className="flex items-start gap-2.5 text-xs leading-relaxed text-muted">
                  <ShieldCheck size={14} className="mt-0.5 shrink-0 text-[var(--accent)]" />
                  <span>{action}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-xs text-faint">No actions are available for this result.</p>
          )}
        </section>

        <section className="panel p-5">
          <div className="flex items-center justify-between gap-2">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <TriangleAlert size={16} className="text-[var(--warn)]" /> Top indicators
            </h3>
            <span className="text-[10px] uppercase tracking-wider text-faint">
              {findings.length} total
            </span>
          </div>
          {top.length ? (
            <div className="mt-3 space-y-2">
              {top.map((finding, index) => (
                <FindingCard key={`${finding.indicator_id}-${index}`} finding={finding} />
              ))}
            </div>
          ) : (
            <div className="mt-2 flex items-start gap-2.5 rounded-lg bg-[var(--panel-soft)] p-3 text-xs leading-relaxed text-muted">
              <ShieldCheck size={16} className="mt-0.5 shrink-0 text-[var(--safe)]" />
              No indicators were raised in the stages that completed. This is not a guarantee of safety.
            </div>
          )}
        </section>

        {assessment.disagreements?.length > 0 && (
          <section className="panel border-[color-mix(in_srgb,var(--warn)_30%,transparent)] p-5">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-[var(--warn)]">
              <Sparkles size={16} /> Engine disagreement
            </h3>
            {assessment.disagreements.map((note) => (
              <p key={note} className="mt-2 text-xs leading-relaxed text-muted">
                {note}
              </p>
            ))}
          </section>
        )}
      </div>

      <div className="space-y-4">
        <section className="panel p-5">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <Layers3 size={16} className="text-[var(--accent)]" /> Category contributions
          </h3>
          <p className="mt-1 text-[10px] leading-relaxed text-faint">
            Highest indicator + half the second + a quarter of the rest within each category.
          </p>
          <div className="mt-4">
            <CategoryBars categories={assessment.categories} />
          </div>
        </section>

        <section className="panel p-5">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <Gauge size={16} className="text-[var(--accent)]" /> Evidence quality
          </h3>
          <div className="mt-3 space-y-2.5 text-xs">
            <div className="flex justify-between gap-3">
              <span className="text-muted">Stages attempted</span>
              <span className="mono">{assessment.evidence_quality?.attempted ?? "—"}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-muted">Completed or partial</span>
              <span className="mono">{assessment.evidence_quality?.completed ?? "—"}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-muted">Completion ratio</span>
              <span className="mono">
                {typeof assessment.evidence_quality?.ratio === "number"
                  ? `${Math.round(assessment.evidence_quality.ratio * 100)}%`
                  : "—"}
              </span>
            </div>
          </div>
          <p className="mt-3 border-t border-[var(--border)] pt-3 text-[10px] leading-relaxed text-faint">
            {assessment.confidence?.explanation ||
              "Confidence is not a statistical probability."}
          </p>
        </section>

        {scan.input_type === "url" && scan.analysis?.normalized_url && (
          <section className="panel p-5">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <Link2 size={16} className="text-[var(--accent)]" /> Destination
            </h3>
            <p className="mono mt-2 break-all text-[11px] leading-relaxed text-muted">
              {scan.analysis.normalized_url}
            </p>
            {scan.analysis.http?.final_url &&
              scan.analysis.http.final_url !== scan.analysis.normalized_url && (
                <p className="mono mt-2 break-all text-[11px] leading-relaxed text-[var(--warn)]">
                  Final: {scan.analysis.http.final_url}
                </p>
              )}
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" className="btn py-1.5 text-[11px]" onClick={onShare}>
                <Share2 size={12} /> Share in community
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function FindingsTab({ scan }) {
  const findings = scan.analysis?.assessment?.supporting_findings || [];
  const [severity, setSeverity] = useState("all");
  const counts = useMemo(() => {
    const map = { all: findings.length };
    findings.forEach((finding) => {
      map[finding.severity] = (map[finding.severity] || 0) + 1;
    });
    return map;
  }, [findings]);
  const filtered = severity === "all" ? findings : findings.filter((item) => item.severity === severity);
  const sevKeys = ["critical", "high", "medium", "low", "info"].filter((key) => counts[key]);

  if (!findings.length) {
    return (
      <div className="panel">
        <EmptyState
          icon={ShieldCheck}
          title="No indicators were raised"
          description="The stages that completed did not produce any explainable indicators. This is not a guarantee that the content is safe."
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 inline-flex items-center gap-1.5 text-[11px] text-faint">
          <Filter size={13} /> Filter
        </span>
        {["all", ...sevKeys].map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setSeverity(key)}
            className={`rounded-full border px-3 py-1 text-[11px] font-semibold transition ${
              severity === key
                ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--text)]"
                : "border-[var(--border)] text-muted hover:text-[var(--text)]"
            }`}
          >
            {key === "all" ? "All" : titleCase(key)} ({counts[key] || 0})
          </button>
        ))}
      </div>
      <div className="space-y-2.5">
        {filtered.map((finding, index) => (
          <FindingCard key={`${finding.indicator_id}-${index}`} finding={finding} />
        ))}
      </div>
      <p className="text-[11px] leading-relaxed text-faint">
        Indicators are observations, not proof. Weight values are internal scoring inputs and are not
        probabilities.
      </p>
    </div>
  );
}

function ReasoningTab({ scan }) {
  const assessment = scan.analysis?.assessment || {};
  const stages = assessment.stages || [];
  const trace = assessment.decision_trace || [];
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <section className="panel p-5">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <ListChecks size={16} className="text-[var(--accent)]" /> Decision trace
        </h3>
        <ol className="mt-3 space-y-3">
          {trace.map((step, index) => (
            <li key={`${step}-${index}`} className="flex gap-3 text-xs leading-relaxed text-muted">
              <span className="mono grid h-6 w-6 shrink-0 place-items-center rounded-full border border-[var(--border)] text-[10px] font-bold text-[var(--accent)]">
                {index + 1}
              </span>
              <span className="pt-1">{step}</span>
            </li>
          ))}
          {!trace.length && <p className="text-xs text-faint">No decision trace was recorded.</p>}
        </ol>
      </section>

      <div className="space-y-4">
        <section className="panel p-5">
          <h3 className="text-sm font-semibold">Scoring policy</h3>
          <dl className="mt-3 space-y-2.5 text-xs">
            <div className="flex justify-between gap-4 border-b border-[var(--border)] pb-2">
              <dt className="text-muted">High-risk threshold</dt>
              <dd className="mono">≥ 70</dd>
            </div>
            <div className="flex justify-between gap-4 border-b border-[var(--border)] pb-2">
              <dt className="text-muted">Suspicious threshold</dt>
              <dd className="mono">≥ 35</dd>
            </div>
            <div className="flex justify-between gap-4 border-b border-[var(--border)] pb-2">
              <dt className="text-muted">Critical finding floor</dt>
              <dd className="mono">85</dd>
            </div>
            <div className="flex justify-between gap-4 border-b border-[var(--border)] pb-2">
              <dt className="text-muted">High finding floor</dt>
              <dd className="mono">40</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-muted">Score kind</dt>
              <dd className="mono">{assessment.score_kind || "heuristic_uncalibrated"}</dd>
            </div>
          </dl>
          <p className="mt-3 text-[10px] leading-relaxed text-faint">
            Scores are capped at 100. Missing essential evidence produces an inconclusive result rather
            than a low score. See the methodology page for the full policy.
          </p>
        </section>

        <section className="panel p-5">
          <h3 className="text-sm font-semibold">Confidence</h3>
          <p className="mt-2 text-xs leading-relaxed text-muted">
            {assessment.confidence?.explanation ||
              "Confidence is based on indicator-category coverage and completed stages."}
          </p>
          <span className="chip mt-3 capitalize">{assessment.confidence?.level || "low"}</span>
        </section>
      </div>

      <section className="panel overflow-hidden xl:col-span-2">
        <div className="border-b border-[var(--border)] px-5 py-3.5">
          <h3 className="text-sm font-semibold">Analysis stages</h3>
        </div>
        <div className="divide-y divide-[var(--border)]">
          {stages.map((stage, index) => (
            <div key={`${stage.name}-${index}`} className="flex flex-col gap-2 px-5 py-3 sm:flex-row sm:items-start">
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold">{stage.name}</p>
                <p className="mt-0.5 text-[11px] leading-relaxed text-muted">{stage.detail}</p>
              </div>
              <StageStatus status={stage.status} />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function LimitationsTab({ scan }) {
  const assessment = scan.analysis?.assessment || {};
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
      <section className="panel p-5">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <ShieldAlert size={16} className="text-[var(--warn)]" /> What this result cannot tell you
        </h3>
        <ul className="mt-3 space-y-2.5">
          {(assessment.limitations || []).map((item) => (
            <li key={item} className="flex items-start gap-2.5 text-xs leading-relaxed text-muted">
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[var(--warn)]" />
              <span>{item}</span>
            </li>
          ))}
          {!assessment.limitations?.length && (
            <li className="text-xs text-faint">No limitations were recorded.</li>
          )}
        </ul>
      </section>
      <div className="space-y-4">
        <section className="panel p-5">
          <h3 className="text-sm font-semibold">Treat with care</h3>
          <p className="mt-2 text-xs leading-relaxed text-muted">
            Automated analysis can produce false positives and false negatives. A clean result does not
            certify a site or message. Verify unexpected requests through an official channel.
          </p>
          <Link to="/about" className="link mt-3 inline-flex items-center gap-1 text-xs">
            Read the methodology <ArrowUpRight size={12} />
          </Link>
        </section>
        <section className="panel p-5">
          <h3 className="text-sm font-semibold">Uncomfortable with this result?</h3>
          <p className="mt-2 text-xs leading-relaxed text-muted">
            If you already interacted with suspicious content, change affected passwords and contact the
            relevant platform. In India, you can start at the national cybercrime portal.
          </p>
          <a
            href="https://cybercrime.gov.in/"
            target="_blank"
            rel="noreferrer noopener"
            className="btn mt-3 w-full py-2 text-xs"
          >
            <ArrowUpRight size={14} /> cybercrime.gov.in
          </a>
        </section>
      </div>
    </div>
  );
}

function ShareModal({ scan, open, onClose }) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const toast = useToast();

  useEffect(() => {
    if (!open) return;
    setTitle(`Suspicious ${inputTypeLabel(scan.input_type).toLowerCase()}: ${scan.input_label}`.slice(0, 160));
    setContent(
      `Shared for community review. Automated classification: ${classificationMeta(scan.classification).label}, heuristic score ${scan.risk_score}/100.\n\n${scan.summary || ""}\n\nThis automated result is not proof and has not been independently verified.`,
    );
    setError("");
  }, [open, scan]);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { data } = await api.createPost({
        title,
        content,
        url: scan.input_type === "url" ? scan.analysis?.normalized_url || "" : "",
        scan_id: scan.id,
      });
      toast.success("Posted to the community. It is marked unverified.");
      onClose();
      navigate(`/community/${data.id}`);
    } catch (apiError) {
      setError(apiError.message || "The post could not be created.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Share this scan in the community"
      description="Community reports are unverified until someone independently analyses them. The linked scan remains owned by your account."
      footer={
        <>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" form="share-scan-form" className="btn btn-primary" disabled={busy}>
            {busy ? <LoaderCircle size={15} className="animate-spin" /> : <Share2 size={15} />}
            {busy ? "Publishing…" : "Publish unverified report"}
          </button>
        </>
      }
    >
      <form id="share-scan-form" onSubmit={submit} className="space-y-4">
        <div>
          <label className="label" htmlFor="share-title">
            Title
          </label>
          <input
            id="share-title"
            className="input"
            value={title}
            maxLength={160}
            minLength={5}
            onChange={(event) => setTitle(event.target.value)}
            required
          />
        </div>
        <div>
          <label className="label" htmlFor="share-content">
            Context
          </label>
          <textarea
            id="share-content"
            className="input min-h-[140px] resize-y"
            value={content}
            maxLength={5000}
            minLength={10}
            onChange={(event) => setContent(event.target.value)}
            required
          />
        </div>
        {error && (
          <p className="rounded-lg border border-[color-mix(in_srgb,var(--danger)_30%,transparent)] bg-[color-mix(in_srgb,var(--danger)_8%,transparent)] p-2.5 text-xs text-[var(--danger)]">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}

export default function Results() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const toast = useToast();
  const [scan, setScan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("overview");
  const [shareOpen, setShareOpen] = useState(false);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api
      .analysis(id)
      .then(({ data }) => {
        if (active) setScan(data);
      })
      .catch((apiError) => {
        if (active) setError(apiError);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id]);

  const download = async () => {
    setDownloading(true);
    try {
      if (getToken()) {
        await downloadAuthenticated(api.scanReportUrl(id), `threatlens-report-${id.slice(0, 8)}.pdf`);
      } else {
        window.open(api.scanReportUrl(id), "_blank", "noopener");
      }
    } catch (apiError) {
      toast.error(apiError.message || "The report could not be downloaded.");
    } finally {
      setDownloading(false);
    }
  };

  const share = () => {
    if (!isAuthenticated) {
      toast.info("Sign in to share a scan in the community.");
      navigate("/login", { state: { from: location.pathname } });
      return;
    }
    if (scan?.is_anonymous) {
      toast.info("Anonymous scans cannot be linked to a community post. Re-run the scan while signed in.");
      return;
    }
    setShareOpen(true);
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-4 w-32" />
        <div className="panel grid gap-0 md:grid-cols-[210px_1fr]">
          <div className="flex items-center justify-center border-b border-[var(--border)] p-6 md:border-b-0 md:border-r">
            <Skeleton className="h-32 w-32 rounded-full" />
          </div>
          <div className="space-y-3 p-6">
            <Skeleton className="h-5 w-28" />
            <Skeleton className="h-7 w-3/4" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
          </div>
        </div>
        <div className="panel h-64" />
      </div>
    );
  }

  if (error) {
    const forbidden = error.status === 403;
    return (
      <div className="panel mx-auto max-w-xl">
        <EmptyState
          icon={forbidden ? ShieldAlert : ScanSearch}
          title={forbidden ? "This scan belongs to another account" : "Scan not found"}
          description={
            forbidden
              ? "Sign in as the account that created this scan. Anonymous scans can only be opened through their private link."
              : "The scan ID is invalid or the scan was deleted. Run a new analysis to continue."
          }
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Link to="/scan" className="btn btn-primary">
                <ScanSearch size={15} /> New scan
              </Link>
              {forbidden && (
                <Link to="/login" className="btn">
                  Sign in
                </Link>
              )}
            </div>
          }
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <Link
          to="/scan"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted transition hover:text-[var(--text)]"
        >
          <ArrowLeft size={14} /> Back to scanner
        </Link>
        <div className="flex flex-wrap gap-2">
          <CopyButton text={window.location.href} />
          <button type="button" className="btn py-2 text-xs" onClick={share}>
            <Share2 size={14} /> Share
          </button>
          <button
            type="button"
            className="btn btn-primary py-2 text-xs"
            onClick={download}
            disabled={downloading}
          >
            {downloading ? <LoaderCircle size={14} className="animate-spin" /> : <Download size={14} />}
            {downloading ? "Preparing…" : "Report PDF"}
          </button>
        </div>
      </div>

      <VerdictHeader scan={scan} />

      <div className="mt-5 flex flex-wrap gap-1 rounded-xl border border-[var(--border)] bg-[var(--panel-soft)] p-1">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setTab(item.id)}
            className={`rounded-lg px-3.5 py-2 text-xs font-semibold transition ${
              tab === item.id
                ? "bg-[var(--bg-elevated)] text-[var(--text)] shadow-sm"
                : "text-muted hover:text-[var(--text)]"
            }`}
          >
            {item.label}
            {item.id === "findings" && (
              <span className="ml-1.5 text-[10px] text-faint">{scan.findings_count || 0}</span>
            )}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {tab === "overview" && <Overview scan={scan} onShare={share} />}
        {tab === "findings" && <FindingsTab scan={scan} />}
        {tab === "evidence" && <ScanEvidence scan={scan} />}
        {tab === "reasoning" && <ReasoningTab scan={scan} />}
        {tab === "limitations" && <LimitationsTab scan={scan} />}
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[var(--border)] bg-[var(--panel-soft)] px-4 py-3 text-xs text-muted">
        <span className="inline-flex items-center gap-2">
          <Lightbulb size={15} className="text-[var(--warn)]" />
          Keep the evidence: the report PDF mirrors this result and its limitations.
        </span>
        {isAuthenticated && (
          <button
            type="button"
            className="btn py-2 text-xs"
            onClick={() => navigate(`/complaints?scan=${scan.id}`)}
          >
            <FileText size={14} /> Start a complaint draft
          </button>
        )}
      </div>

      <ShareModal scan={scan} open={shareOpen} onClose={() => setShareOpen(false)} />
    </div>
  );
}
