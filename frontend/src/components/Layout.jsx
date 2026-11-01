import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  FileText,
  History as HistoryIcon,
  LayoutDashboard,
  LogIn,
  LogOut,
  Menu,
  Moon,
  ScanSearch,
  ShieldCheck,
  Sun,
  UserRound,
  Users,
  X,
} from "lucide-react";
import Logo from "./Logo";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { api } from "../lib/api";

const WORKSPACE = [
  { to: "/scan", label: "Scanner", icon: ScanSearch },
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, protected: true },
  { to: "/history", label: "History", icon: HistoryIcon, protected: true },
];

const COMMUNITY = [
  { to: "/community", label: "Community", icon: Users },
  { to: "/complaints", label: "Complaint drafts", icon: FileText, protected: true },
];

const ACCOUNT = [
  { to: "/profile", label: "Profile", icon: UserRound, protected: true },
];

function initials(name = "") {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") || "TL"
  );
}

function NavGroup({ title, items, isAdmin, onNavigate }) {
  return (
    <div className="space-y-1">
      <p className="px-3 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-faint">{title}</p>
      {items.map(({ to, label, icon: Icon, protected: requiresAuth }) => (
        <NavLink
          key={to}
          to={to}
          onClick={onNavigate}
          className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
          end={to === "/community"}
        >
          <Icon size={17} strokeWidth={2} />
          <span className="flex-1">{label}</span>
          {requiresAuth && <ShieldCheck size={12} className="text-faint" aria-label="Sign-in required" />}
        </NavLink>
      ))}
      {isAdmin && title === "Community" && (
        <NavLink
          to="/moderation"
          onClick={onNavigate}
          className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
        >
          <Activity size={17} strokeWidth={2} />
          <span className="flex-1">Moderation</span>
          <span className="chip border-[color-mix(in_srgb,var(--warn)_35%,transparent)] px-1.5 py-0 text-[9px] text-[var(--warn)]">
            Admin
          </span>
        </NavLink>
      )}
    </div>
  );
}

function SidebarContent({ onNavigate }) {
  const { user, isAuthenticated, isAdmin, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    onNavigate?.();
    navigate("/");
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-[72px] items-center px-5">
        <NavLink to="/" onClick={onNavigate} aria-label="ThreatLens home">
          <Logo size={34} />
        </NavLink>
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 pb-4">
        <NavGroup title="Workspace" items={WORKSPACE} isAdmin={isAdmin} onNavigate={onNavigate} />
        <NavGroup title="Community" items={COMMUNITY} isAdmin={isAdmin} onNavigate={onNavigate} />
        <NavGroup title="Account" items={ACCOUNT} isAdmin={isAdmin} onNavigate={onNavigate} />
      </nav>
      <div className="border-t border-[var(--border)] p-3">
        {isAuthenticated ? (
          <div className="rounded-xl bg-[var(--panel-soft)] p-2.5">
            <div className="flex items-center gap-2.5">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--accent-soft)] text-xs font-bold text-[var(--accent)]">
                {initials(user.display_name)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{user.display_name}</p>
                <p className="truncate text-[11px] text-faint">
                  {isAdmin ? "Administrator" : "Signed in"}
                </p>
              </div>
              <button
                type="button"
                onClick={handleLogout}
                className="btn btn-ghost p-2"
                title="Sign out"
                aria-label="Sign out"
              >
                <LogOut size={15} />
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <p className="px-1 text-[11px] leading-relaxed text-faint">
              Sign in to save scan history, post to the community and draft complaints.
            </p>
            <div className="flex gap-2">
              <NavLink to="/login" onClick={onNavigate} className="btn flex-1 py-2 text-xs">
                <LogIn size={14} /> Sign in
              </NavLink>
              <NavLink to="/register" onClick={onNavigate} className="btn btn-primary flex-1 py-2 text-xs">
                Create account
              </NavLink>
            </div>
          </div>
        )}
        <p className="mt-3 px-1 text-[10px] uppercase tracking-[0.16em] text-faint">
          Local instance · v1.0
        </p>
      </div>
    </div>
  );
}

function RouteLabel() {
  const { pathname } = useLocation();
  const map = [
    ["/scan", "Scanner"],
    ["/dashboard", "Dashboard"],
    ["/history", "Scan history"],
    ["/community", "Community"],
    ["/complaints", "Complaint drafts"],
    ["/moderation", "Moderation"],
    ["/profile", "Profile"],
  ];
  const match = map.find(([prefix]) => pathname.startsWith(prefix));
  return match ? match[1] : "Workspace";
}

export default function Layout() {
  const { theme, toggle } = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [health, setHealth] = useState(null);
  const location = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    let active = true;
    api
      .health()
      .then(({ data }) => {
        if (active) setHealth(data);
      })
      .catch(() => {
        if (active) setHealth({ offline: true });
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const online = health && !health.offline && health.database?.ok;

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[258px_minmax(0,1fr)]">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[258px] border-r border-[var(--border)] bg-[color-mix(in_srgb,var(--bg-elevated)_82%,transparent)] backdrop-blur-xl lg:block">
        <SidebarContent />
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
          <aside className="relative h-full w-[280px] max-w-[84vw] animate-fade-up border-r border-[var(--border)] bg-[var(--bg-elevated)]">
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="btn btn-ghost absolute right-3 top-4 z-10 p-2"
              aria-label="Close navigation"
            >
              <X size={18} />
            </button>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div className="min-w-0 lg:col-start-2">
        <header className="sticky top-0 z-30 flex h-[64px] items-center gap-3 border-b border-[var(--border)] bg-[color-mix(in_srgb,var(--bg)_82%,transparent)] px-4 backdrop-blur-xl sm:px-6">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            className="btn btn-ghost p-2 lg:hidden"
            aria-label="Open navigation"
          >
            <Menu size={20} />
          </button>
          <div className="min-w-0 flex-1">
            <p className="hidden text-[10px] font-semibold uppercase tracking-[0.18em] text-faint sm:block">
              ThreatLens workspace
            </p>
            <p className="truncate text-sm font-semibold">{RouteLabel()}</p>
          </div>

          <span
            className="hidden items-center gap-2 rounded-full border border-[var(--border)] px-3 py-1.5 text-[11px] font-medium text-muted md:inline-flex"
            title={
              online
                ? "The local API and database responded to a health check."
                : "The local API health check did not succeed."
            }
          >
            <span className="relative flex h-2 w-2">
              {online && (
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--safe)] opacity-60" />
              )}
              <span
                className="relative inline-flex h-2 w-2 rounded-full"
                style={{ background: online ? "var(--safe)" : "var(--danger)" }}
              />
            </span>
            {online ? "Local engine online" : "API offline"}
          </span>

          <button
            type="button"
            onClick={toggle}
            className="btn btn-ghost p-2.5"
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            title={theme === "dark" ? "Light theme" : "Dark theme"}
          >
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>

          <button
            type="button"
            onClick={() => navigate(isAuthenticated ? "/scan" : "/login")}
            className="btn btn-primary hidden py-2 text-xs sm:inline-flex"
          >
            <ScanSearch size={15} /> New scan
          </button>
        </header>

        <main className="mx-auto w-full max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
        <footer className="mx-auto flex w-full max-w-[1440px] flex-col gap-2 px-4 pb-8 pt-2 text-[11px] text-faint sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
          <p>ThreatLens produces heuristic indicators, not proof. Inconclusive results are not safety.</p>
          <p>
            For incidents in India,{" "}
            <a
              className="link"
              href="https://cybercrime.gov.in/"
              target="_blank"
              rel="noreferrer noopener"
            >
              cybercrime.gov.in
            </a>
          </p>
        </footer>
      </div>
    </div>
  );
}
