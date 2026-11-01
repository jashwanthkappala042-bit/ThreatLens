import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowUpRight,
  CalendarDays,
  CheckCircle2,
  CircleAlert,
  Download,
  FileText,
  LoaderCircle,
  Lock,
  Plus,
  Send,
  ShieldCheck,
} from "lucide-react";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import { Skeleton } from "../components/Skeleton";
import { api, downloadAuthenticated } from "../lib/api";
import { formatDate } from "../lib/format";
import { useToast } from "../context/ToastContext";

const CATEGORIES = [
  { value: "phishing", label: "Phishing or fraudulent website" },
  { value: "financial_fraud", label: "Financial fraud / payment scam" },
  { value: "identity_theft", label: "Identity theft" },
  { value: "account_takeover", label: "Account takeover" },
  { value: "cyberbullying", label: "Harassment or cyberbullying" },
  { value: "other", label: "Other cybercrime" },
];

function today() {
  const date = new Date();
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 10);
}

const EMPTY_FORM = {
  incident_date: today(),
  incident_category: "phishing",
  suspect_url: "",
  description: "",
  evidence: "",
  financial_loss: "",
};

export default function Complaints() {
  const toast = useToast();
  const [searchParams] = useSearchParams();
  const [form, setForm] = useState(EMPTY_FORM);
  const [drafts, setDrafts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState("");
  const [prefilled, setPrefilled] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.complaints({ per_page: 20 });
      setDrafts(data || []);
    } catch (apiError) {
      setError(apiError.message || "Complaint drafts could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const scanId = searchParams.get("scan");
    if (!scanId) return;
    let active = true;
    api
      .analysis(scanId)
      .then(({ data: scan }) => {
        if (!active) return;
        const analysis = scan.analysis || {};
        const suspectUrl =
          analysis.normalized_url || analysis.extracted_urls?.[0] || "";
        const assessment = analysis.assessment || {};
        const description = [
          `A ThreatLens analysis of “${scan.input_label}” returned “${assessment.classification_label || scan.classification}” with a heuristic score of ${scan.risk_score}/100.`,
          scan.summary,
          "Describe what happened next, whether you interacted with the content, and any loss or harm.",
        ]
          .filter(Boolean)
          .join("\n\n")
          .slice(0, 5000);
        setForm((current) => ({
          ...current,
          suspect_url: suspectUrl || current.suspect_url,
          description,
        }));
        setPrefilled(true);
        toast.info("Draft prefilled from the saved scan. Review every field before generating.");
      })
      .catch(() => {
        if (active) toast.info("The linked scan could not be opened; fill the draft manually.");
      });
    return () => {
      active = false;
    };
  }, [searchParams, toast]);

  const update = (field) => (event) => {
    setForm((current) => ({ ...current, [field]: event.target.value }));
    setFormError("");
  };

  const submit = async (event) => {
    event.preventDefault();
    setFormError("");
    if (form.description.trim().length < 20) {
      setFormError("Describe the incident in at least 20 characters.");
      return;
    }
    if (form.incident_category === "financial_fraud" && !form.financial_loss.trim()) {
      setFormError("Provide an approximate loss amount for financial fraud.");
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.createComplaint({
        ...form,
        description: form.description.trim(),
        evidence: form.evidence.trim(),
        suspect_url: form.suspect_url.trim(),
      });
      toast.success("Complaint draft generated locally. It has not been submitted.");
      setForm({ ...EMPTY_FORM, incident_date: today() });
      setPrefilled(false);
      await load();
      try {
        await downloadAuthenticated(
          api.complaintPdfUrl(data.id),
          `threatlens-complaint-draft-${data.id.slice(0, 8)}.pdf`,
        );
      } catch {
        toast.info("Draft saved. Use the download button in the list to retrieve the PDF.");
      }
    } catch (apiError) {
      setFormError(apiError.message || "The draft could not be generated.");
    } finally {
      setBusy(false);
    }
  };

  const download = async (draft) => {
    setDownloading(draft.id);
    try {
      await downloadAuthenticated(
        api.complaintPdfUrl(draft.id),
        `threatlens-complaint-draft-${draft.id.slice(0, 8)}.pdf`,
      );
    } catch (apiError) {
      toast.error(apiError.message || "The PDF could not be downloaded.");
    } finally {
      setDownloading("");
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Incident response"
        title="Complaint drafts"
        description="Prepare a locally generated draft PDF for your own review. ThreatLens never submits a complaint to an authority."
        actions={
          <a
            href="https://cybercrime.gov.in/"
            target="_blank"
            rel="noreferrer noopener"
            className="btn py-2 text-xs"
          >
            <ArrowUpRight size={14} /> cybercrime.gov.in
          </a>
        }
      />

      <div className="mb-5 flex items-start gap-2.5 rounded-xl border border-[color-mix(in_srgb,var(--warn)_28%,transparent)] bg-[color-mix(in_srgb,var(--warn)_6%,transparent)] px-4 py-3 text-[11px] leading-relaxed text-[var(--warn)]">
        <CircleAlert size={15} className="mt-0.5 shrink-0" />
        <span>
          A draft is not a legal filing. Review and complete it yourself, then use the official portal or
          contact local authorities. Do not upload sensitive evidence to untrusted services.
        </span>
      </div>

      {prefilled && (
        <div className="mb-4 flex items-center gap-2 rounded-xl border border-[var(--accent)] bg-[var(--accent-soft)] px-4 py-2.5 text-[11px] text-[var(--accent)]">
          <CheckCircle2 size={14} /> Prefilled from your saved scan. Check the URL and description carefully.
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.05fr)_minmax(320px,0.95fr)]">
        <form onSubmit={submit} className="panel p-5 sm:p-6">
          <div className="flex items-center gap-2">
            <FileText size={17} className="text-[var(--accent)]" />
            <h2 className="text-base font-semibold">New draft</h2>
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-faint">
            All fields are stored locally. The generated PDF is marked DRAFT.
          </p>

          <div className="mt-5 space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="label" htmlFor="incident-date">
                  Incident date
                </label>
                <input
                  id="incident-date"
                  type="date"
                  className="input"
                  value={form.incident_date}
                  max={today()}
                  onChange={update("incident_date")}
                  required
                />
              </div>
              <div>
                <label className="label" htmlFor="incident-category">
                  Category
                </label>
                <select
                  id="incident-category"
                  className="input"
                  value={form.incident_category}
                  onChange={update("incident_category")}
                >
                  {CATEGORIES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="label" htmlFor="suspect-url">
                Suspect URL <span className="font-normal normal-case tracking-normal">(optional)</span>
              </label>
              <input
                id="suspect-url"
                className="input mono text-xs"
                placeholder="https://example.com/account"
                value={form.suspect_url}
                maxLength={2048}
                onChange={update("suspect_url")}
              />
              <p className="mt-1 text-[10px] text-faint">
                Validated as a URL. Private or malformed addresses are rejected.
              </p>
            </div>

            {form.incident_category === "financial_fraud" && (
              <div>
                <label className="label" htmlFor="financial-loss">
                  Approximate loss
                </label>
                <input
                  id="financial-loss"
                  className="input"
                  placeholder="e.g. INR 4,500"
                  maxLength={120}
                  value={form.financial_loss}
                  onChange={update("financial_loss")}
                  required
                />
              </div>
            )}

            <div>
              <div className="flex items-end justify-between gap-2">
                <label className="label" htmlFor="description">
                  What happened
                </label>
                <span className="mb-1.5 text-[10px] text-faint">{form.description.length} / 5,000</span>
              </div>
              <textarea
                id="description"
                className="input min-h-[180px] resize-y leading-relaxed"
                placeholder="Describe the incident in your own words: what you received, what you did, and any loss or harm."
                minLength={20}
                maxLength={5000}
                value={form.description}
                onChange={update("description")}
                required
              />
            </div>

            <div>
              <label className="label" htmlFor="evidence">
                Evidence notes <span className="font-normal normal-case tracking-normal">(optional)</span>
              </label>
              <textarea
                id="evidence"
                className="input min-h-[90px] resize-y leading-relaxed"
                placeholder="e.g. Screenshot saved locally, message reference, transaction ID."
                maxLength={5000}
                value={form.evidence}
                onChange={update("evidence")}
              />
            </div>

            {formError && (
              <div
                role="alert"
                className="flex items-start gap-2 rounded-lg border border-[color-mix(in_srgb,var(--danger)_30%,transparent)] bg-[color-mix(in_srgb,var(--danger)_8%,transparent)] p-2.5 text-xs text-[var(--danger)]"
              >
                <CircleAlert size={14} className="mt-0.5 shrink-0" /> {formError}
              </div>
            )}

            <button type="submit" className="btn btn-primary w-full py-3" disabled={busy}>
              {busy ? <LoaderCircle size={16} className="animate-spin" /> : <Send size={16} />}
              {busy ? "Generating local draft…" : "Generate draft PDF"}
            </button>
            <div className="flex items-start gap-2 text-[10px] leading-relaxed text-faint">
              <Lock size={12} className="mt-0.5 shrink-0" />
              The PDF is stored privately under this local instance and linked only to your account.
            </div>
          </div>
        </form>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Your drafts</h2>
            <span className="text-[11px] text-faint">{drafts.length} saved</span>
          </div>

          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-32 rounded-2xl" />
              ))}
            </div>
          ) : error ? (
            <div className="panel">
              <EmptyState
                icon={CircleAlert}
                title="Drafts unavailable"
                description={error}
                action={
                  <button type="button" className="btn" onClick={load}>
                    Retry
                  </button>
                }
              />
            </div>
          ) : drafts.length === 0 ? (
            <div className="panel">
              <EmptyState
                icon={FileText}
                title="No drafts yet"
                description="Generate a draft after an incident. It will appear here with a downloadable PDF marked DRAFT."
              />
            </div>
          ) : (
            drafts.map((draft) => (
              <article key={draft.id} className="panel p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="chip text-[var(--warn)]">
                    <FileText size={11} /> Draft · not submitted
                  </span>
                  <span className="text-[10px] text-faint">{formatDate(draft.created_at)}</span>
                </div>
                <h3 className="mt-2 text-sm font-semibold">{draft.incident_category_label}</h3>
                <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-muted">
                  {draft.description}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-faint">
                  <span className="inline-flex items-center gap-1">
                    <CalendarDays size={11} /> Incident {draft.incident_date}
                  </span>
                  {draft.financial_loss && <span>Loss: {draft.financial_loss}</span>}
                </div>
                <div className="mt-3 flex items-center justify-between gap-2 border-t border-[var(--border)] pt-2.5">
                  <span className="mono text-[9px] text-faint">{draft.id.slice(0, 8)}</span>
                  <button
                    type="button"
                    className="btn py-1.5 text-[11px]"
                    onClick={() => download(draft)}
                    disabled={downloading === draft.id}
                  >
                    {downloading === draft.id ? (
                      <LoaderCircle size={12} className="animate-spin" />
                    ) : (
                      <Download size={12} />
                    )}
                    Download PDF
                  </button>
                </div>
              </article>
            ))
          )}

          <div className="panel p-4">
            <div className="flex items-center gap-2 text-xs font-semibold">
              <ShieldCheck size={15} className="text-[var(--accent)]" /> What happens after this?
            </div>
            <p className="mt-1.5 text-[11px] leading-relaxed text-muted">
              Nothing is submitted automatically. Review the PDF, gather evidence and file through the
              official portal or with local authorities if appropriate.
            </p>
            <a
              href="https://cybercrime.gov.in/"
              target="_blank"
              rel="noreferrer noopener"
              className="link mt-2 inline-flex items-center gap-1 text-[11px]"
            >
              Open the national cybercrime portal <ArrowUpRight size={11} />
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
