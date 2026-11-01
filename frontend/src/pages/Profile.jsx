import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  FileSearch,
  FileText,
  KeyRound,
  LoaderCircle,
  LogOut,
  MessagesSquare,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import PageHeader from "../components/PageHeader";
import { Skeleton } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { api } from "../lib/api";
import { formatDate, titleCase } from "../lib/format";

function StatCard({ to, icon: Icon, label, value, hint }) {
  return (
    <Link
      to={to}
      className="panel group flex items-start gap-3 p-4 transition hover:border-[var(--border-strong)]"
    >
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent)]">
        <Icon size={18} />
      </span>
      <div className="min-w-0">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-faint">{label}</p>
        <p className="mt-0.5 text-2xl font-bold leading-none">{value}</p>
        <p className="mt-1 text-[11px] text-muted">{hint}</p>
      </div>
    </Link>
  );
}

export default function Profile() {
  const { user, refreshUser, logout } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();

  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [displayName, setDisplayName] = useState("");
  const [savingName, setSavingName] = useState(false);

  const [passwords, setPasswords] = useState({ current: "", next: "", confirm: "" });
  const [savingPassword, setSavingPassword] = useState(false);
  const [passwordError, setPasswordError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.profile();
      setProfile(data);
      setDisplayName(data.user.display_name);
    } catch (apiError) {
      setError(apiError.message || "Your profile could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const saveName = async (event) => {
    event.preventDefault();
    const trimmed = displayName.trim();
    if (trimmed.length < 2) {
      toast.error("Display names need at least 2 characters.");
      return;
    }
    if (trimmed === profile?.user.display_name) {
      toast.info("That is already your display name.");
      return;
    }
    setSavingName(true);
    try {
      const { data } = await api.updateProfile({ display_name: trimmed });
      setProfile(data);
      await refreshUser();
      toast.success("Display name updated.");
    } catch (apiError) {
      toast.error(apiError.message || "The display name could not be updated.");
    } finally {
      setSavingName(false);
    }
  };

  const savePassword = async (event) => {
    event.preventDefault();
    setPasswordError("");
    if (passwords.next.length < 8) {
      setPasswordError("Use at least 8 characters with at least one letter and one number.");
      return;
    }
    if (passwords.next !== passwords.confirm) {
      setPasswordError("The new password confirmation does not match.");
      return;
    }
    setSavingPassword(true);
    try {
      await api.updateProfile({
        current_password: passwords.current,
        new_password: passwords.next,
      });
      setPasswords({ current: "", next: "", confirm: "" });
      toast.success("Password changed.");
    } catch (apiError) {
      setPasswordError(apiError.message || "The password could not be changed.");
    } finally {
      setSavingPassword(false);
    }
  };

  const endSession = async () => {
    await logout();
    toast.info("Signed out.");
    navigate("/");
  };

  if (loading) {
    return (
      <div>
        <PageHeader eyebrow="Account" title="Profile" description="Manage your local account and session." />
        <div className="grid gap-4 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-24 w-full" />
          ))}
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div>
        <PageHeader eyebrow="Account" title="Profile" />
        <div className="panel">
          <EmptyState
            icon={UserRound}
            title="Could not load your profile"
            description={error || "The API did not return profile data."}
            action={
              <button type="button" className="btn" onClick={load}>
                Retry
              </button>
            }
          />
        </div>
      </div>
    );
  }

  const account = profile.user;
  const counts = profile.counts;

  return (
    <div>
      <PageHeader
        eyebrow="Account"
        title="Profile"
        description="This is a local account on this ThreatLens instance. It is not linked to any external identity provider."
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          to="/history"
          icon={FileSearch}
          label="Saved scans"
          value={counts.scans}
          hint="Open scan history"
        />
        <StatCard
          to="/community"
          icon={MessagesSquare}
          label="Community posts"
          value={counts.posts}
          hint="View the community feed"
        />
        <StatCard
          to="/complaints"
          icon={FileText}
          label="Complaint drafts"
          value={counts.complaints}
          hint="Open complaint drafts"
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <section className="panel p-5">
          <div className="flex items-center gap-2">
            <UserRound size={17} className="text-[var(--accent)]" />
            <h2 className="text-sm font-semibold">Account details</h2>
          </div>

          <dl className="mt-4 space-y-3 text-sm">
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Email</dt>
              <dd className="truncate font-medium">{account.email}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Role</dt>
              <dd>
                <span className="chip">
                  {account.is_admin && <ShieldCheck size={12} className="text-[var(--warn)]" />}
                  {titleCase(account.role)}
                </span>
              </dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Joined</dt>
              <dd className="font-medium">{formatDate(account.created_at, { withTime: false })}</dd>
            </div>
          </dl>

          <form onSubmit={saveName} className="mt-5 border-t border-[var(--border)] pt-4">
            <label className="label" htmlFor="display-name">
              Display name
            </label>
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                id="display-name"
                className="input"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                maxLength={60}
                autoComplete="nickname"
              />
              <button type="submit" className="btn shrink-0 sm:w-auto" disabled={savingName}>
                {savingName ? <LoaderCircle size={15} className="animate-spin" /> : null}
                Save name
              </button>
            </div>
            <p className="mt-2 text-[11px] text-faint">
              Shown next to community posts and comments. Email addresses are never shown publicly.
            </p>
          </form>
        </section>

        <section className="panel p-5">
          <div className="flex items-center gap-2">
            <KeyRound size={17} className="text-[var(--accent)]" />
            <h2 className="text-sm font-semibold">Change password</h2>
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-muted">
            Confirm your current password before setting a new one. Existing sessions stay valid until
            their token expires.
          </p>

          <form onSubmit={savePassword} className="mt-4 space-y-3">
            <div>
              <label className="label" htmlFor="current-password">
                Current password
              </label>
              <input
                id="current-password"
                type="password"
                className="input"
                value={passwords.current}
                onChange={(event) =>
                  setPasswords((current) => ({ ...current, current: event.target.value }))
                }
                autoComplete="current-password"
                required
              />
            </div>
            <div>
              <label className="label" htmlFor="new-password">
                New password
              </label>
              <input
                id="new-password"
                type="password"
                className="input"
                value={passwords.next}
                onChange={(event) => setPasswords((current) => ({ ...current, next: event.target.value }))}
                autoComplete="new-password"
                required
              />
            </div>
            <div>
              <label className="label" htmlFor="confirm-password">
                Confirm new password
              </label>
              <input
                id="confirm-password"
                type="password"
                className="input"
                value={passwords.confirm}
                onChange={(event) =>
                  setPasswords((current) => ({ ...current, confirm: event.target.value }))
                }
                autoComplete="new-password"
                required
              />
            </div>

            {passwordError && (
              <p className="rounded-lg border border-[color-mix(in_srgb,var(--danger)_35%,transparent)] bg-[color-mix(in_srgb,var(--danger)_8%,transparent)] px-3 py-2 text-xs text-[var(--danger)]">
                {passwordError}
              </p>
            )}

            <button type="submit" className="btn btn-primary w-full" disabled={savingPassword}>
              {savingPassword ? <LoaderCircle size={15} className="animate-spin" /> : <KeyRound size={15} />}
              Update password
            </button>
          </form>
        </section>
      </div>

      <section className="panel mt-4 flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold">Session</h2>
          <p className="mt-1 text-xs text-muted">
            Signing out clears the token on this browser. The API records the event in its local audit log.
          </p>
        </div>
        <button type="button" className="btn btn-danger shrink-0" onClick={endSession}>
          <LogOut size={15} /> Sign out
        </button>
      </section>

      {user?.id !== account.id && (
        <p className="mt-3 text-[11px] text-faint">
          The loaded profile does not match the current session. Reload the page to refresh it.
        </p>
      )}
    </div>
  );
}
