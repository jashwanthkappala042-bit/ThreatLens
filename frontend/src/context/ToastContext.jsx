import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { CheckCircle2, Info, TriangleAlert, X } from "lucide-react";

const ToastContext = createContext(null);

const ICONS = {
  success: CheckCircle2,
  error: TriangleAlert,
  info: Info,
};

let nextId = 1;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback(
    (message, tone = "info", timeout = 5200) => {
      const id = nextId++;
      setToasts((current) => [...current.slice(-3), { id, message, tone }]);
      if (timeout) window.setTimeout(() => dismiss(id), timeout);
      return id;
    },
    [dismiss],
  );

  const value = useMemo(
    () => ({
      push,
      success: (message) => push(message, "success"),
      error: (message) => push(message, "error", 7000),
      info: (message) => push(message, "info"),
      dismiss,
    }),
    [push, dismiss],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-[80] flex w-[min(92vw,380px)] flex-col gap-2"
      >
        {toasts.map((toast) => {
          const Icon = ICONS[toast.tone] || Info;
          const color =
            toast.tone === "success"
              ? "var(--safe)"
              : toast.tone === "error"
                ? "var(--danger)"
                : "var(--accent)";
          return (
            <div
              key={toast.id}
              className="panel-solid pointer-events-auto flex animate-fade-up items-start gap-3 border-l-2 p-3.5 text-sm shadow-glow"
              style={{ borderLeftColor: color }}
              role="status"
            >
              <Icon size={17} style={{ color }} className="mt-0.5 shrink-0" />
              <p className="flex-1 leading-snug">{toast.message}</p>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                className="rounded-md p-1 text-faint transition hover:text-[var(--text)]"
                aria-label="Dismiss notification"
              >
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside ToastProvider");
  return context;
}
