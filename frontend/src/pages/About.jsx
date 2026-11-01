import { Link } from "react-router-dom";
import {
  ArrowRight,
  BrainCircuit,
  Database,
  Eye,
  FileWarning,
  Fingerprint,
  Globe2,
  Lock,
  ScanLine,
  ShieldCheck,
  ShieldQuestion,
  Sparkles,
} from "lucide-react";
import PageHeader from "../components/PageHeader";

const STAGES = [
  {
    icon: Fingerprint,
    title: "Input validation",
    body: "URLs are parsed and normalised, messages are length-checked, and images are verified by magic bytes, decoded size and pixel count before analysis.",
  },
  {
    icon: Globe2,
    title: "Static inspection",
    body: "The URL structure, host, scheme, domain shape and path are inspected without contacting the target. This stage cannot fail because of a slow or hostile site.",
  },
  {
    icon: ShieldCheck,
    title: "Bounded live fetch",
    body: "When enabled for public targets, the scanner resolves the host, rejects private and loopback addresses, revalidates every redirect hop, and enforces timeouts, port and response-size limits.",
  },
  {
    icon: Eye,
    title: "Content heuristics",
    body: "HTML forms, credential fields, scripts, iframes and page text are inspected for explainable indicators. Message text is assessed for urgency, payment and credential-request patterns.",
  },
  {
    icon: BrainCircuit,
    title: "Optional local models",
    body: "URL, email and short-message classifiers are used only if compatible artifacts exist on this machine. There is no hosted model and no external reputation API enabled by default.",
  },
  {
    icon: Sparkles,
    title: "Risk engine",
    body: "Findings are grouped, combined with diminishing returns, capped and mapped to a verdict. Missing or failed evidence produces an inconclusive result, never a safe one.",
  },
];

const LIMITATIONS = [
  "The score is an uncalibrated heuristic. It is not a probability and has not been validated against a labelled production corpus on this instance.",
  "“No significant indicators” means the completed stages found nothing notable. It is not proof that a URL, message or image is safe.",
  "URL scanning only inspects public HTTP/HTTPS targets. Private, loopback, link-local and unusual ports are refused by design.",
  "Content behind authentication, JavaScript-only pages, CAPTCHAs and anti-bot walls may not be visible. Browser rendering is an optional, disabled-by-default capability.",
  "QR decoding uses OpenCV. Text extraction from screenshots requires an optional OCR engine, which may not be installed; if nothing can be read, the image result is inconclusive.",
  "Machine-learning output depends on the dataset and training script used. Without a locally trained artifact, the ML stage is reported as unavailable rather than guessed.",
  "Community posts are user-submitted and remain unverified until someone runs an independent scan. There is no guarantee about their accuracy.",
];

const PRIVACY = [
  "All analysis runs on this machine. No scan content is sent to a third-party service by default.",
  "Uploaded images are not persisted. Only metadata, extracted text and discovered URLs are stored with the scan.",
  "Anonymous scans are retrievable by their result link. Signed-in scans are tied to the account that created them.",
  "Community posts, comments and complaint drafts are visible to this instance's database and are not encrypted at rest.",
  "The local audit log records security-relevant events such as sign-ins, moderation actions and complaint generation.",
];

export default function About() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="How it works"
        title="About ThreatLens"
        description="An explainable, local-first triage tool for suspicious links, messages and screenshots. It shows its evidence, states its limits, and never pretends an inconclusive result is a clean bill of health."
        actions={
          <Link to="/scan" className="btn btn-primary py-2 text-xs">
            <ScanLine size={15} /> Open the scanner
          </Link>
        }
      />

      <section className="panel grid-sweep overflow-hidden p-6">
        <span className="chip">
          <ShieldQuestion size={12} className="text-[var(--accent)]" /> Evidence, not verdicts
        </span>
        <h2 className="mt-4 max-w-3xl text-xl font-bold leading-snug sm:text-2xl">
          Three input types, one analysis pipeline, and a written reason for every point of risk.
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">
          ThreatLens accepts a URL, a message or an image. Each input is normalised, checked for safety
          and passed through the stages that apply to it. Findings are collected with a severity, a
          category, a weight and an explanation, then combined by a single documented policy.
        </p>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-bold tracking-tight">Analysis pipeline</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {STAGES.map(({ icon: Icon, title, body }, index) => (
            <article key={title} className="panel p-5">
              <div className="flex items-center gap-2.5">
                <span className="grid h-9 w-9 place-items-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent)]">
                  <Icon size={17} />
                </span>
                <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-faint">
                  Stage {index + 1}
                </span>
              </div>
              <h3 className="mt-3 text-sm font-semibold">{title}</h3>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">{body}</p>
            </article>
          ))}
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="panel p-5">
          <h2 className="text-sm font-semibold">Scoring policy</h2>
          <p className="mt-1.5 text-xs leading-relaxed text-muted">
            The engine deliberately avoids averaging unrelated scores, which hides a single critical
            finding behind many harmless ones.
          </p>
          <ol className="mt-4 space-y-3 text-xs leading-relaxed text-muted">
            <li>
              <span className="font-semibold text-[var(--text)]">1. Group by category.</span> Findings
              such as “credential harvest” or “domain anomaly” are grouped so that repeated variants of
              one problem do not stack linearly.
            </li>
            <li>
              <span className="font-semibold text-[var(--text)]">2. Diminishing returns.</span> Within a
              category the highest weight counts fully, the second at half, and the remainder at a
              quarter.
            </li>
            <li>
              <span className="font-semibold text-[var(--text)]">3. Sum and cap.</span> Category scores
              are summed and capped at 100. Critical and high findings impose conservative floors.
            </li>
            <li>
              <span className="font-semibold text-[var(--text)]">4. Apply thresholds.</span> Scores of 70
              or more are high risk, 35 to 69 are suspicious, and below 35 means no significant indicators
              were found.
            </li>
            <li>
              <span className="font-semibold text-[var(--text)]">5. Refuse false certainty.</span> If an
              essential stage fails, or an image yields no readable content, the verdict becomes
              inconclusive regardless of the score.
            </li>
          </ol>
        </section>

        <section className="panel p-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Lock size={16} className="text-[var(--accent)]" /> Safety and privacy
          </h2>
          <ul className="mt-3 space-y-2.5 text-xs leading-relaxed text-muted">
            {PRIVACY.map((item) => (
              <li key={item} className="flex items-start gap-2">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[var(--accent)]" />
                {item}
              </li>
            ))}
          </ul>
          <div className="mt-4 rounded-xl border border-[var(--border)] bg-[var(--panel-soft)] p-3">
            <p className="flex items-center gap-2 text-[11px] font-semibold">
              <Database size={13} className="text-[var(--accent)]" /> Storage
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-muted">
              Accounts, scans, community content and complaint drafts live in a local SQLite database.
              Generated PDFs are written to the backend storage directory.
            </p>
          </div>
        </section>
      </div>

      <section className="panel p-5">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <FileWarning size={16} className="text-[var(--warn)]" /> Known limitations
        </h2>
        <p className="mt-1.5 text-xs text-muted">
          These are deliberate, documented constraints rather than hidden caveats.
        </p>
        <ul className="mt-4 grid gap-2.5 text-xs leading-relaxed text-muted sm:grid-cols-2">
          {LIMITATIONS.map((item) => (
            <li key={item} className="flex items-start gap-2 rounded-xl bg-[var(--panel-soft)] p-3">
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[var(--warn)]" />
              {item}
            </li>
          ))}
        </ul>
      </section>

      <section className="panel flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold">If you have already lost money or data</h2>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-muted">
            ThreatLens can help you write a draft, but it cannot file a report or contact authorities.
            In India, report cyber fraud at the national portal or call the 1930 helpline as soon as
            possible — early reporting improves the chance of freezing a transfer.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <a
            className="btn btn-primary py-2 text-xs"
            href="https://cybercrime.gov.in/"
            target="_blank"
            rel="noreferrer noopener"
          >
            cybercrime.gov.in <ArrowRight size={14} />
          </a>
          <Link to="/complaints" className="btn py-2 text-xs">
            Draft a complaint
          </Link>
        </div>
      </section>

      <p className="pb-2 text-center text-[11px] leading-relaxed text-faint">
        ThreatLens is a local project, not a certified security product. Its output should support —
        not replace — your own judgement and, where appropriate, professional advice.
      </p>
    </div>
  );
}
