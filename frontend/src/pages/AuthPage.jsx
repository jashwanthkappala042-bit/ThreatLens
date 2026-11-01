import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  CircleAlert,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  Mail,
  ScanLine,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import Logo from "../components/Logo";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";

export default function AuthPage({ mode = "login" }) {
  const isRegister = mode === "register";
  const { login, register, isAuthenticated, booting } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();

  const [form, setForm] = useState({
    display_name: "",
    email: "",
    password: "",
    confirm: "",
  });
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const destination = location.state?.from || "/scan";

  if (!booting && isAuthenticated) {
    return <Navigate to={destination} replace />;
  }

  const update = (field) => (event) => {
    setForm((current) => ({ ...current, [field]: event.target.value }));
    setError("");
  };

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    if (isRegister && form.password !== form.confirm) {
      setError("The password confirmation does not match.");
      return;
    }
    if (isRegister && form.password.length < 8) {
      setError("Use at least 8 characters with at least one letter and one number.");
      return;
    }
    setBusy(true);
    try {
      if (isRegister) {
        await register({
          display_name: form.display_name.trim(),
          email: form.email.trim(),
          password: form.password,
        });
        toast.success("Account created. Your scans can now be saved.");
      } else {
        await login({ email: form.email.trim(), password: form.password });
        toast.success("Signed in.");
      }
      navigate(destination, { replace: true });
    } catch (apiError) {
      setError(apiError.message || "Authentication failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_1.05fr]">
      <div className="relative hidden flex-col justify-between overflow-hidden border-r border-[var(--border)] bg-[var(--bg-elevated)] p-10 lg:flex">
        <div className="absolute inset-0 bg-[radial-gradient(700px_400px_at_15%_10%,rgba(61,214,207,0.12),transparent_65%)]" />
        <Link to="/" className="relative w-fit">
          <Logo size={38} />
        </Link>
        <div className="relative max-w-md">
          <span className="chip">
            <ShieldCheck size={12} className="text-[var(--accent)]" /> Local-first analysis
          </span>
          <h1 className="mt-5 text-4xl font-black leading-[1.08] tracking-[-0.03em]">
            Evidence over
            <br />
            <span className="text-[var(--accent)]">assumptions.</span>
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-muted">
            An account keeps your scan history, community reports and complaint drafts together. The
            analysis engine itself runs locally.
          </p>
          <ul className="mt-7 space-y-3 text-sm text-muted">
            {[
              "Saved history with filters and PDF reports",
              "Community reports marked unverified until analysed",
              "Locally generated complaint drafts — never auto-submitted",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2.5">
                <ShieldCheck size={15} className="mt-0.5 shrink-0 text-[var(--accent)]" />
                {item}
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-[11px] leading-relaxed text-faint">
          ThreatLens produces heuristic indicators, not proof. In an emergency, contact local authorities.
        </p>
      </div>

      <div className="flex flex-col px-4 py-6 sm:px-8 lg:px-12 lg:py-10">
        <div className="flex items-center justify-between lg:hidden">
          <Link to="/">
            <Logo size={32} />
          </Link>
          <Link to="/scan" className="btn btn-ghost py-2 text-xs">
            <ScanLine size={14} /> Scanner
          </Link>
        </div>

        <div className="mx-auto flex w-full max-w-[420px] flex-1 flex-col justify-center py-10">
          <Link
            to="/"
            className="mb-7 inline-flex w-fit items-center gap-1.5 text-xs font-semibold text-muted transition hover:text-[var(--text)]"
          >
            <ArrowLeft size={14} /> Back to overview
          </Link>

          <h2 className="text-3xl font-bold tracking-tight">
            {isRegister ? "Create your workspace" : "Welcome back"}
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            {isRegister
              ? "Save scans, join the community and prepare complaint drafts."
              : "Sign in to reach your saved scan history and drafts."}
          </p>

          <form onSubmit={submit} className="mt-7 space-y-4" noValidate>
            {isRegister && (
              <div>
                <label className="label" htmlFor="display_name">
                  Display name
                </label>
                <div className="relative">
                  <UserRound
                    size={16}
                    className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-faint"
                  />
                  <input
                    id="display_name"
                    className="input pl-10"
                    autoComplete="name"
                    placeholder="Analyst name"
                    value={form.display_name}
                    onChange={update("display_name")}
                    maxLength={60}
                    required
                  />
                </div>
              </div>
            )}

            <div>
              <label className="label" htmlFor="email">
                Email address
              </label>
              <div className="relative">
                <Mail
                  size={16}
                  className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-faint"
                />
                <input
                  id="email"
                  type="email"
                  className="input pl-10"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={form.email}
                  onChange={update("email")}
                  required
                />
              </div>
            </div>

            <div>
              <label className="label" htmlFor="password">
                Password
              </label>
              <div className="relative">
                <LockKeyhole
                  size={16}
                  className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-faint"
                />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  className="input px-10"
                  autoComplete={isRegister ? "new-password" : "current-password"}
                  placeholder={isRegister ? "At least 8 characters" : "Your password"}
                  value={form.password}
                  onChange={update("password")}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((current) => !current)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-faint transition hover:text-[var(--text)]"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
              {isRegister && (
                <p className="mt-1.5 text-[11px] text-faint">
                  Minimum 8 characters, including a letter and a number.
                </p>
              )}
            </div>

            {isRegister && (
              <div>
                <label className="label" htmlFor="confirm">
                  Confirm password
                </label>
                <div className="relative">
                  <LockKeyhole
                    size={16}
                    className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-faint"
                  />
                  <input
                    id="confirm"
                    type={showPassword ? "text" : "password"}
                    className="input pl-10"
                    autoComplete="new-password"
                    placeholder="Repeat password"
                    value={form.confirm}
                    onChange={update("confirm")}
                    required
                  />
                </div>
              </div>
            )}

            {error && (
              <div
                role="alert"
                className="flex items-start gap-2.5 rounded-xl border border-[color-mix(in_srgb,var(--danger)_35%,transparent)] bg-[color-mix(in_srgb,var(--danger)_8%,transparent)] p-3 text-sm text-[var(--danger)]"
              >
                <CircleAlert size={16} className="mt-0.5 shrink-0" />
                <span className="leading-relaxed">{error}</span>
              </div>
            )}

            <button type="submit" className="btn btn-primary w-full py-3" disabled={busy}>
              {busy ? <LoaderCircle size={17} className="animate-spin" /> : null}
              {busy ? (isRegister ? "Creating account…" : "Signing in…") : isRegister ? "Create account" : "Sign in"}
              {!busy && <ArrowRight size={16} />}
            </button>
          </form>

          <p className="mt-5 text-center text-sm text-muted">
            {isRegister ? "Already have an account?" : "New to ThreatLens?"}{" "}
            <Link className="link" to={isRegister ? "/login" : "/register"}>
              {isRegister ? "Sign in" : "Create an account"}
            </Link>
          </p>

          <div className="my-6 flex items-center gap-3">
            <div className="divider flex-1" />
            <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-faint">or</span>
            <div className="divider flex-1" />
          </div>

          <Link to="/scan" className="btn w-full py-2.5 text-sm">
            <ScanLine size={16} /> Continue without signing in
          </Link>
          <p className="mt-3 text-center text-[11px] leading-relaxed text-faint">
            Anonymous scans are saved but accessible only through their private result link.
          </p>
        </div>
      </div>
    </div>
  );
}
