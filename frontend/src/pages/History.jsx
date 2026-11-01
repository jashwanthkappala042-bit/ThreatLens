import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  Download,
  FileSearch,
  LoaderCircle,
  ScanLine,
  Search,
  Trash2,
  X,
} from "lucide-react";
import PageHeader from "../components/PageHeader";
import RiskBadge from "../components/RiskBadge";
import EmptyState from "../components/EmptyState";
import ConfirmDialog from "../components/ConfirmDialog";
import { Skeleton } from "../components/Skeleton";
import { api, downloadAuthenticated } from "../lib/api";
import { formatDate, inputTypeLabel } from "../lib/format";
import { useToast } from "../context/ToastContext";

const CLASSIFICATIONS = [
  { value: "", label: "All verdicts" },
  { value: "malicious", label: "High risk" },
  { value: "suspicious", label: "Suspicious" },
  { value: "no_significant_indicators", label: "No significant indicators" },
  { value: "unknown", label: "Inconclusive" },
];

const TYPES = [
  { value: "", label: "All inputs" },
  { value: "url", label: "URL" },
  { value: "email", label: "Message" },
  { value: "image", label: "Image" },
];

const TYPE_BADGE = { url: "URL", email: "EML", image: "IMG" };

export default function History() {
  const navigate = useNavigate();
  const toast = useToast();
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ page: 1, pages: 1, total: 0, per_page: 10 });
  const [filters, setFilters] = useState({ q: "", classification: "", input_type: "" });
  const [searchInput, setSearchInput] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [downloading, setDownloading] = useState("");

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setFilters((current) => ({ ...current, q: searchInput.trim() }));
      setPage(1);
    }, 350);
    return () => window.clearTimeout(handle);
  }, [searchInput]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await api.history({ page, per_page: 10, ...filters });
      setRows(result.data || []);
      setMeta(result.meta || { page: 1, pages: 1, total: 0, per_page: 10 });
    } catch (apiError) {
      setError(apiError.message || "History could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [page, filters]);

  useEffect(() => {
    load();
  }, [load]);

  const setFilter = (field, value) => {
    setFilters((current) => ({ ...current, [field]: value }));
    setPage(1);
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await api.deleteScan(pendingDelete.id);
      toast.success("Scan deleted.");
      setPendingDelete(null);
      if (rows.length === 1 && page > 1) setPage((current) => current - 1);
      else load();
    } catch (apiError) {
      toast.error(apiError.message || "The scan could not be deleted.");
    } finally {
      setDeleting(false);
    }
  };

  const download = async (scan) => {
    setDownloading(scan.id);
    try {
      await downloadAuthenticated(
        api.scanReportUrl(scan.id),
        `threatlens-report-${scan.id.slice(0, 8)}.pdf`,
      );
    } catch (apiError) {
      toast.error(apiError.message || "The report could not be downloaded.");
    } finally {
      setDownloading("");
    }
  };

  const activeFilters = Boolean(filters.q || filters.classification || filters.input_type);

  return (
    <div>
      <PageHeader
        eyebrow="Your workspace"
        title="Scan history"
        description="Only scans saved to your account appear here. Anonymous scans remain accessible by their private result link."
        actions={
          <Link to="/scan" className="btn btn-primary py-2 text-xs">
            <ScanLine size={15} /> New scan
          </Link>
        }
      />

      <div className="panel mb-4 p-3">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
          <div className="relative min-w-0 flex-1">
            <Search
              size={15}
              className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-faint"
            />
            <input
              className="input py-2.5 pl-10 text-sm"
              placeholder="Search by URL, subject or filename…"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              aria-label="Search scan history"
            />
            {searchInput && (
              <button
                type="button"
                onClick={() => setSearchInput("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-1 text-faint hover:text-[var(--text)]"
                aria-label="Clear search"
              >
                <X size={14} />
              </button>
            )}
          </div>
          <select
            className="input py-2.5 text-sm lg:w-[175px]"
            value={filters.classification}
            onChange={(event) => setFilter("classification", event.target.value)}
            aria-label="Filter by verdict"
          >
            {CLASSIFICATIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <select
            className="input py-2.5 text-sm lg:w-[140px]"
            value={filters.input_type}
            onChange={(event) => setFilter("input_type", event.target.value)}
            aria-label="Filter by input type"
          >
            {TYPES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <span className="shrink-0 px-1 text-[11px] text-faint">
            {meta.total} result{meta.total === 1 ? "" : "s"}
          </span>
        </div>
      </div>

      {error ? (
        <div className="panel">
          <EmptyState
            icon={FileSearch}
            title="Could not load history"
            description={error}
            action={
              <button type="button" className="btn" onClick={load}>
                Retry
              </button>
            }
          />
        </div>
      ) : loading ? (
        <div className="panel space-y-3 p-5">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-12 w-full" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <div className="panel">
          <EmptyState
            icon={FileSearch}
            title={activeFilters ? "No scans match these filters" : "No saved scans yet"}
            description={
              activeFilters
                ? "Try clearing the search or choosing a different verdict or input type."
                : "Scans you run while signed in are saved here with their full evidence and a downloadable report."
            }
            action={
              activeFilters ? (
                <button
                  type="button"
                  className="btn"
                  onClick={() => {
                    setSearchInput("");
                    setFilters({ q: "", classification: "", input_type: "" });
                    setPage(1);
                  }}
                >
                  Clear filters
                </button>
              ) : (
                <Link to="/scan" className="btn btn-primary">
                  <ScanLine size={16} /> Run a scan
                </Link>
              )
            }
          />
        </div>
      ) : (
        <>
          <div className="panel hidden overflow-hidden md:block">
            <table className="w-full table-fixed border-collapse">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className="table-head px-4 py-3">Input</th>
                  <th className="table-head w-[110px] px-3 py-3">Verdict</th>
                  <th className="table-head w-[74px] px-3 py-3 text-right">Score</th>
                  <th className="table-head w-[90px] px-3 py-3 text-right">Findings</th>
                  <th className="table-head w-[160px] px-3 py-3">Created</th>
                  <th className="table-head w-[110px] px-3 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((scan) => (
                  <tr
                    key={scan.id}
                    className="cursor-pointer border-b border-[var(--border)] transition last:border-0 hover:bg-[var(--panel-soft)]"
                    onClick={() => navigate(`/results/${scan.id}`)}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <span className="grid h-7 w-9 shrink-0 place-items-center rounded-md bg-[var(--accent-soft)] text-[9px] font-bold tracking-wide text-[var(--accent)]">
                          {TYPE_BADGE[scan.input_type] || "SCN"}
                        </span>
                        <div className="min-w-0">
                          <p className="truncate text-xs font-semibold">{scan.input_label}</p>
                          <p className="mt-0.5 truncate text-[10px] text-faint">
                            {inputTypeLabel(scan.input_type)} · {scan.input_preview}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <RiskBadge classification={scan.classification} size="sm" showIcon={false} />
                    </td>
                    <td className="mono px-3 py-3 text-right text-xs font-semibold">{scan.risk_score}</td>
                    <td className="px-3 py-3 text-right text-xs text-muted">{scan.findings_count}</td>
                    <td className="px-3 py-3 text-[11px] text-muted">{formatDate(scan.created_at)}</td>
                    <td className="px-3 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          className="btn btn-ghost p-2"
                          aria-label="Download report"
                          title="Download PDF report"
                          onClick={(event) => {
                            event.stopPropagation();
                            download(scan);
                          }}
                          disabled={downloading === scan.id}
                        >
                          {downloading === scan.id ? (
                            <LoaderCircle size={14} className="animate-spin" />
                          ) : (
                            <Download size={14} />
                          )}
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost p-2 text-[var(--danger)]"
                          aria-label="Delete scan"
                          title="Delete scan"
                          onClick={(event) => {
                            event.stopPropagation();
                            setPendingDelete(scan);
                          }}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="space-y-2.5 md:hidden">
            {rows.map((scan) => (
              <div key={scan.id} className="panel p-4">
                <Link to={`/results/${scan.id}`} className="block">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{scan.input_label}</p>
                      <p className="mt-0.5 text-[10px] text-faint">
                        {inputTypeLabel(scan.input_type)} · {formatDate(scan.created_at)}
                      </p>
                    </div>
                    <RiskBadge classification={scan.classification} size="sm" />
                  </div>
                  <div className="mt-3 flex items-center gap-3 text-[11px] text-muted">
                    <span className="mono">Score {scan.risk_score}</span>
                    <span>{scan.findings_count} findings</span>
                  </div>
                </Link>
                <div className="mt-3 flex justify-end gap-1 border-t border-[var(--border)] pt-2">
                  <button type="button" className="btn btn-ghost py-1.5 text-[11px]" onClick={() => download(scan)}>
                    <Download size={13} /> PDF
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost py-1.5 text-[11px] text-[var(--danger)]"
                    onClick={() => setPendingDelete(scan)}
                  >
                    <Trash2 size={13} /> Delete
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 flex flex-col items-center justify-between gap-3 sm:flex-row">
            <p className="text-[11px] text-faint">
              Page {meta.page} of {meta.pages} · showing {rows.length} of {meta.total}
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="btn py-2 text-xs"
                disabled={meta.page <= 1}
                onClick={() => setPage((current) => current - 1)}
              >
                <ChevronLeft size={14} /> Previous
              </button>
              <button
                type="button"
                className="btn py-2 text-xs"
                disabled={meta.page >= meta.pages}
                onClick={() => setPage((current) => current + 1)}
              >
                Next <ChevronRight size={14} />
              </button>
            </div>
          </div>
        </>
      )}

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        onConfirm={confirmDelete}
        busy={deleting}
        title="Delete this scan?"
        description={
          pendingDelete
            ? `“${pendingDelete.input_label}” and its analysis will be permanently removed from your history. Community posts that linked to it are not deleted.`
            : ""
        }
        confirmLabel="Delete scan"
      />
    </div>
  );
}
