import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  CircleAlert,
  FileImage,
  Image as ImageIcon,
  Info,
  Link2,
  LoaderCircle,
  Mail,
  ScanLine,
  ShieldCheck,
  Sparkles,
  Trash2,
  UploadCloud,
} from "lucide-react";
import PageHeader from "../components/PageHeader";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";

const TABS = [
  { id: "url", label: "URL / website", icon: Link2, hint: "Inspect a link and, when reachable, the page it serves." },
  { id: "email", label: "Email / message", icon: Mail, hint: "Analyse text, sender details and links inside a message." },
  { id: "image", label: "Image / QR", icon: ImageIcon, hint: "Decode QR codes and, when enabled, read screenshot text." },
];

const LOADING_NOTES = [
  "Validating the destination before any network request…",
  "Collecting page structure and explainable indicators…",
  "Applying the documented risk policy…",
];

export default function Scanner() {
  const [tab, setTab] = useState("url");
  const [url, setUrl] = useState("");
  const [email, setEmail] = useState({ subject: "", sender: "", body: "" });
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState("");
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [noteIndex, setNoteIndex] = useState(0);
  const [health, setHealth] = useState(null);
  const inputRef = useRef(null);
  const navigate = useNavigate();
  const toast = useToast();
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    api
      .health()
      .then(({ data }) => setHealth(data.capabilities))
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (!busy) {
      setNoteIndex(0);
      return undefined;
    }
    const interval = window.setInterval(
      () => setNoteIndex((current) => Math.min(current + 1, LOADING_NOTES.length - 1)),
      2400,
    );
    return () => window.clearInterval(interval);
  }, [busy]);

  useEffect(() => {
    if (!file) {
      setPreview("");
      return undefined;
    }
    const objectUrl = URL.createObjectURL(file);
    setPreview(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  const selectTab = (id) => {
    if (busy) return;
    setTab(id);
    setError("");
  };

  const chooseFile = (candidate) => {
    if (!candidate) return;
    if (!candidate.type.startsWith("image/")) {
      setError("Choose a PNG, JPEG, WEBP, GIF, BMP or TIFF image.");
      return;
    }
    if (candidate.size > 5 * 1024 * 1024) {
      setError("The image must be 5 MB or smaller.");
      return;
    }
    setError("");
    setFile(candidate);
  };

  const onDrop = (event) => {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files?.[0]);
  };

  const onPaste = (event) => {
    if (tab !== "image") return;
    const image = Array.from(event.clipboardData?.items || []).find((item) =>
      item.type.startsWith("image/"),
    );
    if (image) {
      event.preventDefault();
      chooseFile(image.getAsFile());
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    setError("");

    if (tab === "url" && !url.trim()) {
      setError("Enter a URL to scan.");
      return;
    }
    if (tab === "email" && !email.subject.trim() && !email.body.trim()) {
      setError("Provide a subject or message body.");
      return;
    }
    if (tab === "image" && !file) {
      setError("Attach an image or paste a screenshot.");
      return;
    }

    setBusy(true);
    try {
      let result;
      if (tab === "url") {
        result = await api.scanUrl(url.trim());
      } else if (tab === "email") {
        result = await api.scanEmail(email);
      } else {
        result = await api.scanImage(file);
      }
      toast.success("Analysis complete.");
      navigate(`/results/${result.data.id}`);
    } catch (apiError) {
      setError(apiError.message || "The scan could not be completed.");
    } finally {
      setBusy(false);
    }
  };

  const activeTab = TABS.find((item) => item.id === tab);

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        eyebrow="Unified scanner"
        title="What are you checking?"
        description="One workspace for links, messages and images. Every result keeps its evidence, engine status and limitations attached."
        actions={
          isAuthenticated ? (
            <Link to="/history" className="btn py-2 text-xs">
              Saved scans
            </Link>
          ) : (
            <Link to="/login" className="btn py-2 text-xs">
              Sign in to save history
            </Link>
          )
        }
      />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_310px]">
        <div className="panel overflow-hidden">
          <div
            role="tablist"
            aria-label="Scan type"
            className="grid gap-1 border-b border-[var(--border)] p-2 sm:grid-cols-3"
          >
            {TABS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                onClick={() => selectTab(id)}
                disabled={busy}
                className={`flex items-center justify-center gap-2 rounded-xl px-3 py-3 text-sm font-semibold transition ${
                  tab === id
                    ? "bg-[var(--accent-soft)] text-[var(--text)] shadow-[inset_0_-2px_0_var(--accent)]"
                    : "text-muted hover:bg-[var(--panel-soft)] hover:text-[var(--text)]"
                }`}
              >
                <Icon size={17} /> {label}
              </button>
            ))}
          </div>

          <form onSubmit={submit} onPaste={onPaste} className="p-5 sm:p-7">
            <div className="mb-5 flex items-start gap-2.5 rounded-xl border border-[var(--border)] bg-[var(--panel-soft)] p-3 text-xs leading-relaxed text-muted">
              <Info size={15} className="mt-0.5 shrink-0 text-[var(--accent)]" />
              {activeTab.hint}
            </div>

            {tab === "url" && (
              <div className="animate-fade-up">
                <label className="label" htmlFor="scan-url">
                  URL to inspect
                </label>
                <div className="relative">
                  <Link2
                    size={18}
                    className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-faint"
                  />
                  <input
                    id="scan-url"
                    className="input py-3.5 pl-11 pr-4 text-[15px] mono"
                    placeholder="https://example.com/account/verify"
                    value={url}
                    onChange={(event) => setUrl(event.target.value)}
                    disabled={busy}
                    autoComplete="off"
                    spellCheck={false}
                    maxLength={2048}
                  />
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-faint">
                  <span>Only http/https.</span>
                  <span>Private, loopback and reserved addresses are blocked.</span>
                  <span>Redirects are revalidated at every hop.</span>
                </div>
              </div>
            )}

            {tab === "email" && (
              <div className="animate-fade-up space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="label" htmlFor="subject">
                      Subject <span className="font-normal normal-case tracking-normal">(optional)</span>
                    </label>
                    <input
                      id="subject"
                      className="input"
                      value={email.subject}
                      maxLength={300}
                      placeholder="Your account will be suspended"
                      onChange={(event) => setEmail({ ...email, subject: event.target.value })}
                      disabled={busy}
                    />
                  </div>
                  <div>
                    <label className="label" htmlFor="sender">
                      Sender <span className="font-normal normal-case tracking-normal">(optional)</span>
                    </label>
                    <input
                      id="sender"
                      className="input"
                      value={email.sender}
                      maxLength={300}
                      placeholder="Security Team <alert@example.com>"
                      onChange={(event) => setEmail({ ...email, sender: event.target.value })}
                      disabled={busy}
                    />
                  </div>
                </div>
                <div>
                  <div className="flex items-end justify-between gap-2">
                    <label className="label" htmlFor="body">
                      Message text
                    </label>
                    <span className="mb-1.5 text-[10px] text-faint">{email.body.length} / 20,000</span>
                  </div>
                  <textarea
                    id="body"
                    className="input min-h-[190px] resize-y leading-relaxed"
                    placeholder="Paste the full message. Links and sender details are analysed too."
                    value={email.body}
                    maxLength={20000}
                    onChange={(event) => setEmail({ ...email, body: event.target.value })}
                    disabled={busy}
                  />
                </div>
              </div>
            )}

            {tab === "image" && (
              <div className="animate-fade-up">
                {!file ? (
                  <button
                    type="button"
                    onClick={() => inputRef.current?.click()}
                    onDragOver={(event) => {
                      event.preventDefault();
                      setDragging(true);
                    }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={onDrop}
                    disabled={busy}
                    className={`flex w-full flex-col items-center justify-center rounded-2xl border border-dashed px-6 py-14 text-center transition ${
                      dragging
                        ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                        : "border-[var(--border-strong)] bg-[var(--panel-soft)] hover:border-[var(--accent)]"
                    }`}
                  >
                    <span className="grid h-12 w-12 place-items-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent)]">
                      <UploadCloud size={23} />
                    </span>
                    <span className="mt-4 text-sm font-semibold">Drop an image here, or browse</span>
                    <span className="mt-1 max-w-sm text-xs leading-relaxed text-faint">
                      Screenshot, QR code or photo. PNG, JPEG, WEBP, GIF, BMP or TIFF · 5 MB max. You can
                      also paste an image with Ctrl+V.
                    </span>
                  </button>
                ) : (
                  <div className="grid gap-4 sm:grid-cols-[200px_1fr] sm:items-start">
                    <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--panel-soft)]">
                      <img
                        src={preview || undefined}
                        alt="Selected upload preview"
                        className="h-40 w-full object-contain sm:h-44"
                      />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-start gap-2.5">
                        <FileImage size={17} className="mt-0.5 shrink-0 text-[var(--accent)]" />
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold">{file.name}</p>
                          <p className="mt-0.5 text-[11px] text-faint">
                            {file.type || "unknown MIME"} · {(file.size / 1024).toFixed(1)} KB
                          </p>
                        </div>
                      </div>
                      <p className="mt-3 text-xs leading-relaxed text-muted">
                        The original image is processed in memory for analysis and is not stored by the
                        backend. Only extracted text and metadata are retained with the scan.
                      </p>
                      <div className="mt-4 flex gap-2">
                        <button
                          type="button"
                          className="btn py-2 text-xs"
                          onClick={() => inputRef.current?.click()}
                          disabled={busy}
                        >
                          Replace
                        </button>
                        <button
                          type="button"
                          className="btn btn-danger py-2 text-xs"
                          onClick={() => setFile(null)}
                          disabled={busy}
                        >
                          <Trash2 size={13} /> Remove
                        </button>
                      </div>
                    </div>
                  </div>
                )}
                <input
                  ref={inputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif,image/bmp,image/tiff"
                  className="sr-only"
                  onChange={(event) => {
                    chooseFile(event.target.files?.[0]);
                    event.target.value = "";
                  }}
                />
              </div>
            )}

            {error && (
              <div
                role="alert"
                className="mt-5 flex items-start gap-2.5 rounded-xl border border-[color-mix(in_srgb,var(--danger)_35%,transparent)] bg-[color-mix(in_srgb,var(--danger)_8%,transparent)] p-3 text-sm text-[var(--danger)]"
              >
                <CircleAlert size={16} className="mt-0.5 shrink-0" />
                <span className="leading-relaxed">{error}</span>
              </div>
            )}

            <div className="mt-6 flex flex-col gap-3 border-t border-[var(--border)] pt-5 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-[11px] leading-relaxed text-faint">
                {isAuthenticated
                  ? "This scan will be saved to your account history."
                  : "Scanning anonymously. The result link is private but not listed in any history."}
              </p>
              <button type="submit" className="btn btn-primary min-w-[170px] py-3" disabled={busy}>
                {busy ? (
                  <>
                    <LoaderCircle size={17} className="animate-spin" /> Analysing…
                  </>
                ) : (
                  <>
                    <ScanLine size={17} /> Run analysis
                  </>
                )}
              </button>
            </div>
          </form>
        </div>

        <aside className="space-y-4">
          {busy ? (
            <div className="panel grid-sweep p-5">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <LoaderCircle size={16} className="animate-spin text-[var(--accent)]" />
                Analysis in progress
              </div>
              <p className="mt-2 text-xs leading-relaxed text-muted">{LOADING_NOTES[noteIndex]}</p>
              <div className="mt-4 space-y-2">
                <div className="skeleton h-2.5 w-full" />
                <div className="skeleton h-2.5 w-4/5" />
                <div className="skeleton h-2.5 w-3/5" />
              </div>
              <p className="mt-4 text-[10px] leading-relaxed text-faint">
                Scans run synchronously. Retrieving a slow website can take several seconds.
              </p>
            </div>
          ) : (
            <div className="panel p-5">
              <div className="flex items-center gap-2">
                <Sparkles size={16} className="text-[var(--accent)]" />
                <h2 className="text-sm font-semibold">What you will see</h2>
              </div>
              <ul className="mt-3 space-y-2.5 text-xs leading-relaxed text-muted">
                {[
                  "A heuristic score and the category contributions behind it",
                  "Each indicator with severity, source and evidence",
                  "Engine status, limitations and disagreement notes",
                  "A downloadable report with the same evidence",
                ].map((item) => (
                  <li key={item} className="flex gap-2">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[var(--accent)]" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="panel p-5">
            <div className="flex items-center gap-2">
              <ShieldCheck size={16} className="text-[var(--accent)]" />
              <h2 className="text-sm font-semibold">Local capabilities</h2>
            </div>
            <div className="mt-3 space-y-2.5">
              <Capability
                label="QR decoding"
                status={health ? "available" : "unknown"}
                detail={health ? "OpenCV" : "Backend offline"}
              />
              <Capability
                label="Screenshot OCR"
                status={health?.ocr?.enabled ? "available" : "optional"}
                detail={
                  health
                    ? health.ocr?.enabled
                      ? health.ocr?.installed
                        ? "EasyOCR enabled"
                        : "Enabled but not installed"
                      : "Disabled by default"
                    : "Backend offline"
                }
              />
              <Capability
                label="Browser rendering"
                status={health?.browser_analysis?.available ? "available" : "optional"}
                detail={health?.browser_analysis?.reason || "Disabled by default"}
              />
              <Capability
                label="Local ML models"
                status={
                  health
                    ? Object.values(health.local_models || {}).some((item) => item?.available)
                      ? "available"
                      : "optional"
                    : "unknown"
                }
                detail={
                  health
                    ? Object.entries(health.local_models || {})
                        .filter(([, item]) => item?.available)
                        .map(([key]) => key.replace("_model", "").toUpperCase())
                        .join(" · ") || "No trained artifacts"
                    : "Backend offline"
                }
              />
              <Capability label="External reputation" status="optional" detail="Not configured" />
            </div>
            <p className="mt-4 border-t border-[var(--border)] pt-3 text-[10px] leading-relaxed text-faint">
              Optional engines are reported honestly. A missing engine is never treated as a clean
              result.
            </p>
          </div>

          <div className="panel p-5">
            <div className="flex items-center gap-2">
              <Info size={16} className="text-[var(--warn)]" />
              <h2 className="text-sm font-semibold">A result is not proof</h2>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-muted">
              Legitimate sites can trigger indicators, and a quiet scan can miss a targeted attack.
              Verify unexpected requests through an official channel you type yourself.
            </p>
          </div>
        </aside>
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[var(--border)] bg-[var(--panel-soft)] px-4 py-3 text-xs text-muted">
        <span>Want the underlying methodology and limitations?</span>
        <Link to="/about" className="link inline-flex items-center gap-1">
          Read how scoring works <ArrowRight size={13} />
        </Link>
      </div>
    </div>
  );
}

function Capability({ label, status, detail }) {
  const color =
    status === "available" ? "var(--safe)" : status === "optional" ? "var(--warn)" : "var(--faint)";
  return (
    <div className="flex items-start gap-2.5">
      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: color }} />
      <div className="min-w-0">
        <p className="text-xs font-medium">{label}</p>
        <p className="truncate text-[10px] text-faint" title={detail}>
          {detail}
        </p>
      </div>
    </div>
  );
}
