import { Link } from "react-router-dom";
import {
  ArrowRight,
  BadgeCheck,
  Braces,
  CircleAlert,
  Eye,
  FileSearch,
  Fingerprint,
  Image as ImageIcon,
  Laptop,
  Link2,
  Mail,
  ScanLine,
  ShieldCheck,
  Sparkles,
  Waypoints,
} from "lucide-react";
import ScoreGauge from "../components/ScoreGauge";
import { useAuth } from "../context/AuthContext";

const INPUTS = [
  {
    icon: Link2,
    title: "Links & websites",
    text: "SSRF-guarded retrieval, redirect-by-redirect validation, HTML structure, form destinations and JavaScript patterns.",
  },
  {
    icon: Mail,
    title: "Messages & email",
    text: "Urgency, impersonation, credential requests, lookalike senders and links extracted from the message body.",
  },
  {
    icon: ImageIcon,
    title: "Screenshots & QR codes",
    text: "Local QR decoding, optional OCR and text analysis. Uploaded images are analysed in memory and not stored.",
  },
];

const STEPS = [
  {
    number: "01",
    title: "Collect only what is needed",
    text: "The analysis pipeline validates schemes, ports and destinations before any request. Redirects are re-checked at every hop.",
  },
  {
    number: "02",
    title: "Separate observation from inference",
    text: "Every signal carries its source, severity, category and evidence. Heuristics, ML output and unknowns never blur together.",
  },
  {
    number: "03",
    title: "Explain the verdict",
    text: "A documented scoring policy groups indicators, applies diminishing returns and refuses to call missing evidence safe.",
  },
];

const FEATURES = [
  {
    icon: Fingerprint,
    title: "Explainable by design",
    text: "Inspect the indicator, its category, severity, source and weight. Follow the decision trace to the final score.",
  },
  {
    icon: Laptop,
    title: "Local-first",
    text: "Runs on your machine with SQLite. No external reputation provider is enabled by default, and no scan is sent to a third party.",
  },
  {
    icon: Eye,
    title: "Inconclusive is a real outcome",
    text: "If a page is unreachable or no image content can be extracted, the result is unknown — never silently marked safe.",
  },
  {
    icon: Braces,
    title: "Inspectable evidence",
    text: "HTTP status, redirect chains, form actions, extracted text and engine status are available for review and PDF export.",
  },
];

function PreviewCard() {
  return (
    <div className="relative">
      <div className="absolute -inset-6 -z-10 rounded-[2rem] bg-[radial-gradient(closest-side,rgba(61,214,207,0.16),transparent)] blur-2xl" />
      <div className="panel grid-sweep overflow-hidden">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3.5">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-[var(--danger)]/70" />
            <span className="h-2 w-2 rounded-full bg-[var(--warn)]/70" />
            <span className="h-2 w-2 rounded-full bg-[var(--safe)]/70" />
          </div>
          <span className="mono text-[10px] uppercase tracking-[0.18em] text-faint">
            Interface preview · not a live scan
          </span>
        </div>
        <div className="grid gap-4 p-5 sm:grid-cols-[auto_1fr] sm:items-center">
          <ScoreGauge score={78} classification="malicious" size={168} />
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="chip" style={{ color: "var(--accent)" }}>
                URL
              </span>
              <span className="chip text-[var(--muted)]">Heuristic score</span>
            </div>
            <p className="mono truncate text-xs text-muted">https://secure-paypal-verify.example/login</p>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              Multiple independent indicator categories were observed. The automated assessment cannot
              prove malicious intent.
            </p>
          </div>
        </div>
        <div className="space-y-2 border-t border-[var(--border)] p-5 pt-4">
          {[
            ["Brand name in hostname outside official domain", "Impersonation", "Medium"],
            ["Password form served over unencrypted HTTP", "Credentials", "Critical"],
            ["Form submits to a different domain", "Credentials", "High"],
          ].map(([title, category, severity]) => (
            <div
              key={title}
              className="flex items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--panel-soft)] px-3 py-2.5"
            >
              <CircleAlert size={15} className="shrink-0 text-[var(--warn)]" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium">{title}</p>
                <p className="text-[10px] uppercase tracking-wider text-faint">{category}</p>
              </div>
              <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--warn)]">
                {severity}
              </span>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-2 border-t border-[var(--border)] bg-[var(--panel-soft)] px-5 py-3 text-[11px] text-faint">
          <BadgeCheck size={14} className="text-[var(--accent)]" />
          Evidence, limitations and decision trace stay attached to the result.
        </div>
      </div>
    </div>
  );
}

export default function Landing() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="space-y-20 pb-8 lg:space-y-24">
      <section className="grid items-center gap-10 pt-4 lg:grid-cols-[1.05fr_0.95fr] lg:gap-14 lg:pt-8">
        <div className="animate-fade-up">
          <span className="inline-flex items-center gap-2 rounded-full border border-[var(--border-strong)] bg-[var(--panel-soft)] px-3 py-1.5 text-[11px] font-semibold tracking-wide text-muted">
            <Sparkles size={13} className="text-[var(--accent)]" />
            Explainable threat analysis · local-first
          </span>
          <h1 className="mt-5 text-4xl font-black leading-[1.05] tracking-[-0.03em] sm:text-5xl xl:text-[58px]">
            See the threat
            <br />
            <span className="bg-gradient-to-r from-[#7ee7e1] via-[#3dd6cf] to-[#0f958f] bg-clip-text text-transparent">
              before you click.
            </span>
          </h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-muted">
            ThreatLens inspects suspicious links, messages and screenshots, then shows you the evidence
            behind every indicator. One workspace. No black-box verdicts.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <Link to="/scan" className="btn btn-primary px-5 py-3">
              <ScanLine size={18} /> Start a scan <ArrowRight size={16} />
            </Link>
            {isAuthenticated ? (
              <Link to="/dashboard" className="btn px-5 py-3">
                Open dashboard
              </Link>
            ) : (
              <Link to="/register" className="btn px-5 py-3">
                Create an account
              </Link>
            )}
          </div>
          <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px] text-faint">
            <span className="inline-flex items-center gap-1.5">
              <ShieldCheck size={13} className="text-[var(--accent)]" /> Anonymous scan available
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Waypoints size={13} className="text-[var(--accent)]" /> Per-hop SSRF checks
            </span>
            <span className="inline-flex items-center gap-1.5">
              <FileSearch size={13} className="text-[var(--accent)]" /> Real PDF reports
            </span>
          </div>
        </div>
        <PreviewCard />
      </section>

      <section>
        <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--accent)]">
              One scanner
            </p>
            <h2 className="mt-1.5 text-2xl font-bold tracking-tight">Three ways in. One risk model.</h2>
          </div>
          <p className="max-w-md text-sm leading-relaxed text-muted">
            Paste a URL, drop in a message or upload an image. ThreatLens normalises the evidence before
            applying the same documented scoring policy.
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {INPUTS.map(({ icon: Icon, title, text }) => (
            <div key={title} className="panel group p-5 transition hover:border-[var(--border-strong)]">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent)]">
                <Icon size={19} />
              </span>
              <h3 className="mt-4 text-base font-semibold">{title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{text}</p>
              <Link
                to="/scan"
                className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--accent)]"
              >
                Scan now <ArrowRight size={13} className="transition group-hover:translate-x-0.5" />
              </Link>
            </div>
          ))}
        </div>
      </section>

      <section className="panel overflow-hidden">
        <div className="grid gap-0 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="border-b border-[var(--border)] p-6 sm:p-8 lg:border-b-0 lg:border-r">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--accent)]">
              How it works
            </p>
            <h2 className="mt-2 text-2xl font-bold tracking-tight">
              Evidence first.
              <br />
              Score second.
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-muted">
              A verdict without its reasoning is just another thing to trust. ThreatLens keeps the
              observations visible at every step.
            </p>
            <div className="mt-6 flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--panel-soft)] p-3 text-[11px] leading-relaxed text-muted">
              <CircleAlert size={15} className="shrink-0 text-[var(--warn)]" />
              The score is heuristic and uncalibrated. It is not a probability of maliciousness.
            </div>
          </div>
          <div className="divide-y divide-[var(--border)]">
            {STEPS.map((step) => (
              <div key={step.number} className="flex gap-4 p-6 sm:p-7">
                <span className="mono shrink-0 text-xs font-bold tracking-widest text-[var(--accent)]">
                  {step.number}
                </span>
                <div>
                  <h3 className="font-semibold">{step.title}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-muted">{step.text}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section>
        <div className="mb-6">
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--accent)]">
            Built for scrutiny
          </p>
          <h2 className="mt-1.5 text-2xl font-bold tracking-tight">Designed to show its work.</h2>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <div key={title} className="panel p-5">
              <Icon size={18} className="text-[var(--accent)]" />
              <h3 className="mt-3 text-sm font-semibold">{title}</h3>
              <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="relative overflow-hidden rounded-3xl border border-[var(--border-strong)] bg-[linear-gradient(135deg,rgba(61,214,207,0.12),rgba(10,16,27,0.2)_55%,rgba(51,104,255,0.1))] p-7 sm:p-10">
        <div className="absolute -right-16 -top-16 h-64 w-64 rounded-full bg-[radial-gradient(closest-side,rgba(61,214,207,0.2),transparent)]" />
        <div className="relative flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-center">
          <div className="max-w-xl">
            <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">Check the next thing you receive.</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              Start with a URL, a message or an image. Results stay available for your account, and
              anonymous scans remain reachable through their private link.
            </p>
          </div>
          <Link to="/scan" className="btn btn-primary shrink-0 px-5 py-3">
            <ScanLine size={18} /> Open scanner
          </Link>
        </div>
      </section>
    </div>
  );
}
