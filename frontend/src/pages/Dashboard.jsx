import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  BarChart3,
  CircleAlert,
  Clock3,
  Eye,
  Radar,
  ScanLine,
  ShieldAlert,
  Sparkles,
  TrendingUp,
  Users,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import PageHeader from "../components/PageHeader";
import RiskBadge from "../components/RiskBadge";
import EmptyState from "../components/EmptyState";
import { Skeleton } from "../components/Skeleton";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { classificationMeta, relativeTime, titleCase } from "../lib/format";

const PIE_COLORS = {
  malicious: "var(--danger)",
  suspicious: "var(--warn)",
  no_significant_indicators: "var(--safe)",
  unknown: "var(--faint)",
};

const CHART_TICK = { fontSize: 10, fill: "var(--faint)" };

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-[var(--border-strong)] bg-[var(--panel-solid)] px-3 py-2 shadow-lg">
      {label && <p className="text-[10px] uppercase tracking-wider text-faint">{label}</p>}
      {payload.map((item) => (
        <p key={item.name || item.dataKey} className="mt-0.5 text-xs font-semibold">
          {item.name || item.dataKey}: <span className="mono">{item.value}</span>
        </p>
      ))}
    </div>
  );
}

function Kpi({ label, value, hint, icon: Icon, tone = "var(--accent)" }) {
  return (
    <div className="panel p-4 sm:p-5">
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-faint">{label}</p>
        <Icon size={16} style={{ color: tone }} />
      </div>
      <p className="mt-2.5 text-2xl font-bold tracking-tight">{value}</p>
      <p className="mt-1 text-[11px] leading-relaxed text-faint">{hint}</p>
    </div>
  );
}

function RecentScanRow({ scan }) {
  return (
    <Link
      to={`/results/${scan.id}`}
      className="flex items-center gap-3 border-b border-[var(--border)] px-4 py-3 text-sm transition last:border-0 hover:bg-[var(--panel-soft)]"
    >
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[var(--accent-soft)] text-[10px] font-bold uppercase text-[var(--accent)]">
        {scan.input_type === "url" ? "URL" : scan.input_type === "email" ? "EML" : "IMG"}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-semibold">{scan.input_label}</p>
        <p className="mt-0.5 truncate text-[10px] text-faint">
          {relativeTime(scan.created_at)} · {scan.findings_count} indicator
          {scan.findings_count === 1 ? "" : "s"}
        </p>
      </div>
      <div className="hidden shrink-0 sm:block">
        <RiskBadge classification={scan.classification} size="sm" />
      </div>
      <span className="mono w-8 shrink-0 text-right text-xs font-semibold text-muted">
        {scan.risk_score}
      </span>
    </Link>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    Promise.all([
      api.dashboardStats(),
      api.dashboardActivity(),
      api.dashboardCategories(),
      api.dashboardOverview(),
    ])
      .then(([stats, activity, categories, overview]) => {
        if (!active) return;
        setData({
          stats: stats.data,
          activity: activity.data,
          categories: categories.data,
          overview: overview.data,
        });
      })
      .catch((apiError) => {
        if (active) setError(apiError.message || "The dashboard could not be loaded.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-8 w-56" />
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-28 rounded-2xl" />
          ))}
        </div>
        <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
          <Skeleton className="h-80 rounded-2xl" />
          <Skeleton className="h-80 rounded-2xl" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="panel">
        <EmptyState
          icon={CircleAlert}
          title="Dashboard unavailable"
          description={error}
          action={
            <button type="button" className="btn" onClick={() => window.location.reload()}>
              Try again
            </button>
          }
        />
      </div>
    );
  }

  const { stats, activity, categories, overview } = data;
  const counts = stats.counts || {};
  const pieData = Object.entries(counts)
    .filter(([, value]) => value > 0)
    .map(([key, value]) => ({
      key,
      name: classificationMeta(key).short,
      value,
      color: PIE_COLORS[key],
    }));
  const empty = stats.total_scans === 0;

  return (
    <div>
      <PageHeader
        eyebrow="Operations overview"
        title={`Welcome back, ${user?.display_name?.split(" ")[0] || "analyst"}`}
        description="Saved scans from your account only. Anonymous scans are excluded from these statistics."
        actions={
          <Link to="/scan" className="btn btn-primary py-2 text-xs">
            <ScanLine size={15} /> New scan
          </Link>
        }
      />

      {empty ? (
        <div className="panel">
          <EmptyState
            icon={Radar}
            title="No saved scans yet"
            description="Run your first analysis while signed in and this dashboard will fill with your real scan history, classifications and indicator categories."
            action={
              <Link to="/scan" className="btn btn-primary">
                <ScanLine size={16} /> Run a scan
              </Link>
            }
          />
          {overview.community_posts?.length > 0 && (
            <div className="border-t border-[var(--border)] p-5">
              <h3 className="text-sm font-semibold">Recent community reports</h3>
              <div className="mt-3 space-y-2">
                {overview.community_posts.map((post) => (
                  <Link
                    key={post.id}
                    to={`/community/${post.id}`}
                    className="block rounded-lg border border-[var(--border)] p-3 transition hover:border-[var(--border-strong)]"
                  >
                    <p className="text-xs font-semibold">{post.title}</p>
                    <p className="mt-1 text-[10px] text-faint">
                      Unverified · {relativeTime(post.created_at)}
                    </p>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi
              label="Total scans"
              value={stats.total_scans}
              hint="Saved analyses in your account"
              icon={Eye}
            />
            <Kpi
              label="Flagged"
              value={stats.flagged_scans}
              hint="Suspicious or high-risk verdicts"
              icon={ShieldAlert}
              tone="var(--danger)"
            />
            <Kpi
              label="Last 7 days"
              value={stats.scans_last_7_days}
              hint="Scans created in the last week"
              icon={TrendingUp}
            />
            <Kpi
              label="Average score"
              value={stats.average_risk_score}
              hint="Heuristic, uncalibrated, out of 100"
              icon={Activity}
              tone="var(--warn)"
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.35fr_1fr]">
            <section className="panel p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold">Scan activity</h3>
                  <p className="mt-0.5 text-[11px] text-faint">Scans per day · last 14 days</p>
                </div>
                <span className="chip">
                  <Clock3 size={11} /> {activity.range_days} day window
                </span>
              </div>
              <div className="mt-4 h-[260px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={activity.days} margin={{ top: 8, right: 6, left: -22, bottom: 0 }}>
                    <defs>
                      <linearGradient id="activityFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 5" stroke="var(--border)" vertical={false} />
                    <XAxis
                      dataKey="date"
                      tick={CHART_TICK}
                      tickFormatter={(value) => value.slice(5)}
                      axisLine={false}
                      tickLine={false}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      allowDecimals={false}
                      tick={CHART_TICK}
                      axisLine={false}
                      tickLine={false}
                      width={34}
                    />
                    <Tooltip content={<ChartTooltip />} labelFormatter={(label) => `Date ${label}`} />
                    <Area
                      type="monotone"
                      dataKey="count"
                      name="Scans"
                      stroke="var(--accent)"
                      strokeWidth={2}
                      fill="url(#activityFill)"
                      dot={{ r: 2.5, fill: "var(--accent)", strokeWidth: 0 }}
                      activeDot={{ r: 4 }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section className="panel p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold">Classification mix</h3>
                  <p className="mt-0.5 text-[11px] text-faint">All saved scans</p>
                </div>
                <BarChart3 size={16} className="text-[var(--accent)]" />
              </div>
              {pieData.length ? (
                <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_auto] sm:items-center">
                  <div className="h-[200px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={pieData}
                          dataKey="value"
                          nameKey="name"
                          innerRadius={52}
                          outerRadius={78}
                          paddingAngle={3}
                          stroke="var(--bg-elevated)"
                          strokeWidth={2}
                        >
                          {pieData.map((entry) => (
                            <Cell key={entry.key} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip content={<ChartTooltip />} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <ul className="space-y-2">
                    {pieData.map((entry) => (
                      <li key={entry.key} className="flex items-center gap-2 text-[11px]">
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{ background: entry.color }}
                        />
                        <span className="flex-1 text-muted">{entry.name}</span>
                        <span className="mono font-semibold">{entry.value}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="mt-6 text-xs text-faint">No classification data yet.</p>
              )}
            </section>
          </div>

          <div className="grid gap-4 xl:grid-cols-[1fr_1.35fr]">
            <section className="panel p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold">Indicator categories</h3>
                  <p className="mt-0.5 text-[11px] text-faint">
                    Medium, high and critical findings by category
                  </p>
                </div>
                <Sparkles size={16} className="text-[var(--accent)]" />
              </div>
              {categories.length ? (
                <div className="mt-4 h-[230px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={categories}
                      layout="vertical"
                      margin={{ top: 0, right: 12, left: 6, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 5" stroke="var(--border)" horizontal={false} />
                      <XAxis type="number" allowDecimals={false} tick={CHART_TICK} axisLine={false} tickLine={false} />
                      <YAxis
                        type="category"
                        dataKey="category"
                        width={96}
                        tick={CHART_TICK}
                        tickFormatter={titleCase}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip content={<ChartTooltip />} />
                      <Bar dataKey="count" name="Findings" radius={[0, 6, 6, 0]} barSize={14}>
                        {categories.map((entry) => (
                          <Cell key={entry.category} fill="var(--accent)" fillOpacity={0.75} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="mt-6 text-xs text-faint">
                  No medium-or-higher findings have been recorded yet.
                </p>
              )}
            </section>

            <section className="panel overflow-hidden">
              <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3.5">
                <h3 className="text-sm font-semibold">Recent scans</h3>
                <Link to="/history" className="link inline-flex items-center gap-1 text-[11px]">
                  View history <ArrowRight size={12} />
                </Link>
              </div>
              {overview.recent_scans?.length ? (
                <div>
                  {overview.recent_scans.map((scan) => (
                    <RecentScanRow key={scan.id} scan={scan} />
                  ))}
                </div>
              ) : (
                <p className="px-4 py-8 text-center text-xs text-faint">No scans yet.</p>
              )}
            </section>
          </div>

          {overview.community_posts?.length > 0 && (
            <section className="panel p-5">
              <div className="flex items-center justify-between">
                <h3 className="flex items-center gap-2 text-sm font-semibold">
                  <Users size={16} className="text-[var(--accent)]" /> Recent community reports
                </h3>
                <Link to="/community" className="link text-[11px]">
                  Open feed
                </Link>
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-3">
                {overview.community_posts.map((post) => (
                  <Link
                    key={post.id}
                    to={`/community/${post.id}`}
                    className="rounded-xl border border-[var(--border)] p-3 transition hover:border-[var(--border-strong)]"
                  >
                    <p className="line-clamp-2 text-xs font-semibold leading-snug">{post.title}</p>
                    <p className="mt-2 text-[10px] text-faint">
                      Unverified · {relativeTime(post.created_at)} · {post.comment_count} comments
                    </p>
                  </Link>
                ))}
              </div>
            </section>
          )}

          <p className="flex items-start gap-2 rounded-xl border border-[var(--border)] bg-[var(--panel-soft)] px-4 py-3 text-[11px] leading-relaxed text-faint">
            <CircleAlert size={14} className="mt-0.5 shrink-0 text-[var(--warn)]" />
            These charts aggregate your saved scans. They do not represent global threat activity, and the
            risk score is not a calibrated probability.
          </p>
        </div>
      )}
    </div>
  );
}
