import { useState } from "react";
import {
  Braces,
  CheckCircle2,
  CircleDashed,
  Clock3,
  ExternalLink,
  FileWarning,
  Image as ImageIcon,
  Link2,
  Mail,
  QrCode,
  ServerCrash,
} from "lucide-react";
import { Link } from "react-router-dom";
import { formatDate, titleCase } from "../lib/format";

function Section({ title, icon: Icon, children, action }) {
  return (
    <section className="panel overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--border)] px-5 py-3.5">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          {Icon && <Icon size={15} className="text-[var(--accent)]" />}
          {title}
        </h3>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

function Value({ value }) {
  if (value === null || value === undefined || value === "") {
    return <span className="text-faint">—</span>;
  }
  if (typeof value === "boolean") {
    return (
      <span style={{ color: value ? "var(--warn)" : "var(--muted)" }}>{value ? "Yes" : "No"}</span>
    );
  }
  if (typeof value === "number") return <span className="mono">{value.toLocaleString()}</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-faint">none</span>;
    return (
      <span className="flex flex-wrap gap-1">
        {value.slice(0, 12).map((item, index) => (
          <span key={index} className="chip px-2 py-0.5 font-normal normal-case">
            {typeof item === "object" ? JSON.stringify(item).slice(0, 60) : String(item)}
          </span>
        ))}
        {value.length > 12 && <span className="text-faint">+{value.length - 12} more</span>}
      </span>
    );
  }
  if (typeof value === "object") {
    return (
      <span className="mono text-[11px] text-muted" title={JSON.stringify(value)}>
        {JSON.stringify(value).slice(0, 140)}
        {JSON.stringify(value).length > 140 ? "…" : ""}
      </span>
    );
  }
  return <span className="break-words">{String(value)}</span>;
}

function KeyValues({ entries }) {
  return (
    <dl className="grid gap-x-6 gap-y-2.5 sm:grid-cols-2">
      {entries.map(([label, value]) => (
        <div key={label} className="min-w-0 border-b border-[var(--border)] pb-2 last:border-0">
          <dt className="text-[10px] font-semibold uppercase tracking-[0.12em] text-faint">
            {titleCase(label)}
          </dt>
          <dd className="mt-1 text-xs leading-relaxed">
            <Value value={value} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function StageStatus({ status }) {
  const config = {
    completed: { color: "var(--safe)", icon: CheckCircle2, label: "Completed" },
    partial: { color: "var(--warn)", icon: Clock3, label: "Partial" },
    failed: { color: "var(--danger)", icon: ServerCrash, label: "Failed" },
    unavailable: { color: "var(--faint)", icon: FileWarning, label: "Unavailable" },
    skipped: { color: "var(--faint)", icon: CircleDashed, label: "Skipped" },
  }[status] || { color: "var(--faint)", icon: CircleDashed, label: status || "Unknown" };
  const Icon = config.icon;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold"
      style={{
        color: config.color,
        borderColor: `color-mix(in srgb, ${config.color} 32%, transparent)`,
        background: `color-mix(in srgb, ${config.color} 8%, transparent)`,
      }}
    >
      <Icon size={11} /> {config.label}
    </span>
  );
}

function LinkList({ urls }) {
  if (!urls?.length) return <p className="text-xs text-faint">No URLs were extracted.</p>;
  return (
    <ul className="space-y-2">
      {urls.map((url) => (
        <li key={url} className="flex items-start gap-2 rounded-lg bg-[var(--panel-soft)] px-3 py-2">
          <Link2 size={13} className="mt-0.5 shrink-0 text-[var(--accent)]" />
          <span className="mono min-w-0 break-all text-[11px] leading-relaxed">{url}</span>
        </li>
      ))}
    </ul>
  );
}

function UrlResults({ results }) {
  if (!results?.length) return null;
  return (
    <div className="space-y-3">
      {results.map((result, index) => {
        const assessment = result.assessment || result;
        return (
          <div key={index} className="rounded-xl border border-[var(--border)] p-3">
            <p className="mono break-all text-[11px] text-[var(--accent)]">{result.url}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-faint">
              {result.status && <span>status: {result.status}</span>}
              {result.error && <span className="text-[var(--danger)]">{result.error}</span>}
              {assessment?.classification && <span>classification: {assessment.classification}</span>}
              {typeof assessment?.risk_score === "number" && <span>score: {assessment.risk_score}</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function RawJson({ analysis }) {
  return (
    <details className="panel group overflow-hidden">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-3.5 text-sm font-semibold">
        <span className="flex items-center gap-2">
          <Braces size={15} className="text-[var(--accent)]" /> Raw analysis JSON
        </span>
        <span className="text-[10px] font-normal uppercase tracking-wider text-faint group-open:hidden">
          Show
        </span>
      </summary>
      <div className="border-t border-[var(--border)] p-4">
        <pre className="mono max-h-[480px] overflow-auto whitespace-pre-wrap break-all text-[10px] leading-relaxed text-muted">
          {JSON.stringify(analysis, null, 2)}
        </pre>
      </div>
    </details>
  );
}

function BackendObservation({ item }) {
  return (
    <div className="flex items-start gap-2.5 rounded-lg bg-[var(--panel-soft)] px-3 py-2 text-xs">
      <span
        className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ background: item.status === "completed" ? "var(--safe)" : "var(--warn)" }}
      />
      <div className="min-w-0 flex-1">
        <p className="font-medium">{item.name}</p>
        <p className="mt-0.5 leading-relaxed text-muted">{item.detail || item.reason || ""}</p>
      </div>
      <StageStatus status={item.status} />
    </div>
  );
}

export default function ScanEvidence({ scan }) {
  const analysis = scan.analysis || {};
  const assessment = analysis.assessment || {};

  return (
    <div className="space-y-4">
      {scan.input_type === "url" && <UrlEvidence analysis={analysis} />}
      {scan.input_type === "email" && <EmailEvidence analysis={analysis} />}
      {scan.input_type === "image" && <ImageEvidence analysis={analysis} />}

      <Section title="Assessment engines" icon={ServerCrash}>
        <div className="space-y-2">
          {(assessment.engine_results || []).map((item, index) => (
            <BackendObservation key={`${item.name}-${index}`} item={item} />
          ))}
          {assessment.ml && (
            <div className="mt-3 rounded-lg border border-[var(--border)] p-3 text-xs">
              <p className="font-semibold">Machine-learning output</p>
              <p className="mt-1 leading-relaxed text-muted">
                {assessment.ml.available
                  ? `Predicted “${assessment.ml.predicted_label}” with a raw model score of ${assessment.ml.probability}. This is uncalibrated and is not a probability of maliciousness.`
                  : assessment.ml.reason || "No trained model artifact is configured."}
              </p>
            </div>
          )}
        </div>
      </Section>

      <RawJson analysis={analysis} />
    </div>
  );
}

function UrlEvidence({ analysis }) {
  const features = analysis.features || {};
  const http = analysis.http || {};
  const html = analysis.html || {};
  const favicon = analysis.favicon || {};
  const browser = analysis.browser || {};

  const featureEntries = [
    ["normalized_url", analysis.normalized_url],
    ["hostname", analysis.hostname],
    ["registrable_domain", analysis.registrable_domain],
    ["scheme", analysis.scheme],
    ["tld", features.tld],
    ["resolved_ips", analysis.resolved_ips],
    ["url_length", features.url_length],
    ["hostname_length", features.hostname_length],
    ["path_length", features.path_length],
    ["subdomain_count", features.subdomain_count],
    ["hyphens", features.hyphens],
    ["digits", features.digits],
    ["https", features.https],
    ["punycode", features.punycode],
    ["is_ip_literal", features.is_ip_literal],
    ["suspicious_tld", features.suspicious_tld],
    ["shortener", features.shortener],
    ["brand_in_hostname", features.brand_in_hostname],
    ["brand_in_path", features.brand_in_path],
    ["risky_extension", features.risky_extension],
  ].filter(([, value]) => value !== undefined);

  return (
    <>
      <Section title="URL structure" icon={Link2}>
        <KeyValues entries={featureEntries} />
      </Section>

      <Section title="HTTP response" icon={ExternalLink}>
        {http.available ? (
          <div className="space-y-4">
            <KeyValues
              entries={[
                ["status_code", http.status_code],
                ["final_url", http.final_url],
                ["final_hostname", http.final_hostname],
                ["content_type", http.content_type],
                ["response_bytes", http.response_bytes],
                ["elapsed_ms", http.elapsed_ms],
                ["content_truncated", http.content_truncated],
              ]}
            />
            {http.redirect_chain?.length > 0 && (
              <div>
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-faint">
                  Redirect chain
                </p>
                <ol className="space-y-1.5">
                  {http.redirect_chain.map((hop, index) => (
                    <li
                      key={index}
                      className="flex items-center gap-2 rounded-lg bg-[var(--panel-soft)] px-3 py-2 text-[11px]"
                    >
                      <span className="mono w-5 shrink-0 text-faint">{index + 1}</span>
                      <span className="mono w-10 shrink-0 text-[var(--accent)]">{hop.status}</span>
                      <span className="mono min-w-0 break-all">{hop.url}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            {http.headers && (
              <details>
                <summary className="cursor-pointer text-[11px] font-semibold text-muted">
                  Response headers
                </summary>
                <pre className="mono mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-[var(--panel-soft)] p-3 text-[10px] leading-relaxed">
                  {JSON.stringify(http.headers, null, 2)}
                </pre>
              </details>
            )}
          </div>
        ) : (
          <div className="flex items-start gap-2.5 text-xs leading-relaxed text-[var(--muted)]">
            <ServerCrash size={16} className="mt-0.5 shrink-0 text-[var(--danger)]" />
            <div>
              <p className="font-semibold text-[var(--danger)]">Page could not be retrieved</p>
              <p className="mt-1">{http.error || "No HTTP observation is available."}</p>
              <p className="mt-1 text-faint">
                The URL structure was still inspected. Missing page content is not evidence of safety.
              </p>
            </div>
          </div>
        )}
      </Section>

      <Section title="HTML & form structure" icon={FileWarning}>
        {html.available ? (
          <div className="space-y-4">
            <KeyValues
              entries={[
                ["title", html.title],
                ["meta_description", html.meta_description],
                ["form_count", html.form_count],
                ["password_field_count", html.password_field_count],
                ["hidden_input_count", html.hidden_input_count],
                ["external_link_count", html.external_link_count],
                ["script_count", html.script_count],
                ["inline_script_count", html.inline_script_count],
                ["iframes", html.iframes?.length],
                ["meta_refresh", html.meta_refresh],
                ["js_pattern_hits", html.js_pattern_hits],
              ]}
            />
            {html.forms?.length > 0 && (
              <div>
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-faint">
                  Forms
                </p>
                <div className="space-y-2">
                  {html.forms.map((form, index) => (
                    <div key={index} className="rounded-lg border border-[var(--border)] p-3 text-[11px]">
                      <p className="mono break-all">{form.action}</p>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        <span className="chip px-2 py-0.5 font-normal normal-case">{form.method}</span>
                        {form.has_password && (
                          <span className="chip px-2 py-0.5 font-normal normal-case text-[var(--warn)]">
                            password field
                          </span>
                        )}
                        {form.external_action && (
                          <span className="chip px-2 py-0.5 font-normal normal-case text-[var(--danger)]">
                            external destination
                          </span>
                        )}
                        {form.field_names?.slice(0, 8).map((name) => (
                          <span key={name} className="chip px-2 py-0.5 font-normal normal-case">
                            {name}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {html.visible_text && (
              <div>
                <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-faint">
                  Visible text excerpt
                </p>
                <p className="max-h-36 overflow-auto rounded-lg bg-[var(--panel-soft)] p-3 text-[11px] leading-relaxed text-muted">
                  {html.visible_text}
                </p>
              </div>
            )}
            {html.external_links?.length > 0 && (
              <div>
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-faint">
                  External links (first {html.external_links.length})
                </p>
                <ul className="space-y-1.5">
                  {html.external_links.map((link) => (
                    <li key={link.url} className="rounded-lg bg-[var(--panel-soft)] px-3 py-2">
                      <p className="mono break-all text-[10px] text-[var(--accent)]">{link.url}</p>
                      {link.text && <p className="mt-0.5 text-[10px] text-faint">{link.text}</p>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <p className="text-xs leading-relaxed text-muted">
            {html.reason || "No HTML document was available to inspect."}
          </p>
        )}
      </Section>

      <Section title="Optional browser & favicon checks" icon={ImageIcon}>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-[var(--border)] p-3">
            <p className="text-xs font-semibold">Favicon</p>
            <p className="mt-1 break-words text-[11px] leading-relaxed text-muted">
              {favicon.collected
                ? favicon.final_url || favicon.declared_url || "Collected."
                : favicon.reason || "Not collected."}
            </p>
            {favicon.sha256 && (
              <p className="mono mt-1 break-all text-[9px] text-faint">sha256: {favicon.sha256}</p>
            )}
          </div>
          <div className="rounded-lg border border-[var(--border)] p-3">
            <p className="text-xs font-semibold">Browser analysis</p>
            <p className="mt-1 text-[11px] leading-relaxed text-muted">
              {browser.available
                ? `${browser.network_requests?.length || 0} network requests and ${browser.console_messages?.length || 0} console messages observed.`
                : browser.reason || "Unavailable or disabled by configuration."}
            </p>
          </div>
        </div>
      </Section>
    </>
  );
}

function EmailEvidence({ analysis }) {
  const input = analysis.input || {};
  const features = analysis.features || {};
  const ml = analysis.ml || {};

  return (
    <>
      <Section title="Message under analysis" icon={Mail}>
        <div className="space-y-3">
          <KeyValues
            entries={[
              ["subject", input.subject],
              ["sender", input.sender],
            ]}
          />
          <div>
            <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-faint">
              Body preview (first 1,000 characters)
            </p>
            <p className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-[var(--panel-soft)] p-3 text-[11px] leading-relaxed text-muted">
              {input.body_preview || "No body text supplied."}
            </p>
          </div>
        </div>
      </Section>

      <Section title="Text features" icon={Braces}>
        {Object.keys(features).length ? (
          <KeyValues entries={Object.entries(features)} />
        ) : (
          <p className="text-xs text-faint">No text features were produced.</p>
        )}
      </Section>

      <Section title="Extracted links" icon={Link2}>
        <LinkList urls={analysis.extracted_urls} />
        {analysis.url_results?.length > 0 && (
          <div className="mt-4">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-faint">
              Link inspection
            </p>
            <UrlResults results={analysis.url_results} />
          </div>
        )}
      </Section>

      <Section title="Text classifier" icon={ServerCrash}>
        {ml.available ? (
          <>
            <p className="text-xs leading-relaxed text-muted">
              {`Class “${ml.predicted_label}” at a raw score of ${ml.probability}. Model metadata: ${
                ml.model?.name || "unnamed"
              }${ml.model?.dataset ? `, trained on ${ml.model.dataset}` : ""}. This score is not statistically calibrated.`}
            </p>
            {ml.class_probabilities && (
              <div className="mt-3 flex flex-wrap gap-2">
                {Object.entries(ml.class_probabilities).map(([name, value]) => (
                  <span key={name} className="chip">
                    {name}: {value}
                  </span>
                ))}
              </div>
            )}
          </>
        ) : (
          <p className="text-xs leading-relaxed text-muted">
            {ml.reason || "No trained email model is configured. Results rely on documented heuristics."}
          </p>
        )}
      </Section>
    </>
  );
}

function ImageEvidence({ analysis }) {
  const file = analysis.file || {};
  const ml = analysis.ml || {};

  return (
    <>
      <Section title="Image metadata" icon={ImageIcon}>
        <KeyValues
          entries={[
            ["filename", file.filename],
            ["actual_format", file.actual_format],
            ["declared_type", file.declared_type],
            ["dimensions", file.width && file.height ? `${file.width} × ${file.height}px` : undefined],
            ["bytes", file.bytes],
            ["analysis_max_dimension", file.analysis_max_dimension],
            ["sha256", file.sha256],
          ]}
        />
        <p className="mt-3 text-[11px] leading-relaxed text-faint">
          The uploaded image is not persisted. This hash identifies the analysed bytes; it is not a
          reputation lookup.
        </p>
      </Section>

      <Section title="QR decoding" icon={QrCode}>
        {analysis.qr_values?.length ? (
          <ul className="space-y-2">
            {analysis.qr_values.map((value) => (
              <li
                key={value}
                className="mono break-all rounded-lg bg-[var(--panel-soft)] px-3 py-2 text-[11px]"
              >
                {value}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-faint">No QR code was decoded from this image.</p>
        )}
      </Section>

      <Section title="OCR text" icon={FileWarning}>
        {analysis.ocr_text ? (
          <p className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-[var(--panel-soft)] p-3 text-[11px] leading-relaxed text-muted">
            {analysis.ocr_text}
          </p>
        ) : (
          <p className="text-xs leading-relaxed text-muted">
            No OCR text is available. OCR is an optional component and is disabled by default; without
            it, screenshot text cannot be assessed.
          </p>
        )}
      </Section>

      <Section title="Extracted links" icon={Link2}>
        <LinkList urls={analysis.extracted_urls} />
        {analysis.url_results?.length > 0 && (
          <div className="mt-4">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-faint">
              Link inspection
            </p>
            <UrlResults results={analysis.url_results} />
          </div>
        )}
      </Section>

      {ml.available && (
        <Section title="Image content classifier" icon={ServerCrash}>
          <p className="text-xs text-muted">
            Class “{ml.predicted_label}” at a raw score of {ml.probability}. Uncalibrated.
          </p>
        </Section>
      )}
    </>
  );
}
