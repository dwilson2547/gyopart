import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

// ── formatting ────────────────────────────────────────────────────────────────────────────────

const _txt = typeof document !== "undefined" ? document.createElement("textarea") : null;

/** Catalogue names carry HTML entities ("C 32 AMG&reg;"): decode for display, send the stored name back. */
export function decodeEntities(s: string | null | undefined): string {
  if (!s) return "";
  if (!_txt || !s.includes("&")) return s;
  _txt.innerHTML = s;
  return _txt.value;
}

export function keyLabel(k: { make: string | null; model: string | null; series: string | null; trim?: string | null }): string {
  const name = [k.make, k.model].filter(Boolean).join(" ") || "(blank)";
  if (k.trim) return `${name} · “${k.trim}”`;
  return k.series ? `${name} · ${k.series}` : name;
}

export const fmtInt = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString());

export function years(lo: number | null | undefined, hi: number | null | undefined): string {
  if (lo == null && hi == null) return "—";
  if (lo === hi || hi == null) return String(lo);
  if (lo == null) return String(hi);
  return `${lo}–${hi}`;
}

/** "2001–2009, 2012" from a sorted list of years. */
export function yearSpans(list: number[]): string {
  const out: string[] = [];
  let start: number | null = null, prev: number | null = null;
  for (const y of list) {
    if (start === null) start = y;
    else if (prev !== null && y !== prev + 1) { out.push(years(start, prev)); start = y; }
    prev = y;
  }
  if (start !== null) out.push(years(start, prev));
  return out.join(", ") || "none";
}

// ── data loading ──────────────────────────────────────────────────────────────────────────────

/** Load on mount and whenever `key` changes; stale responses are dropped. */
export function useLoad<T>(fetcher: () => Promise<T>, key: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const fetchRef = useRef(fetcher);
  fetchRef.current = fetcher;

  const load = useCallback(async () => {
    const mine = ++seq.current;
    setLoading(true);
    try {
      const d = await fetchRef.current();
      if (mine === seq.current) { setData(d); setError(null); }
    } catch (e) {
      if (mine === seq.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [key, load]);
  return { data, error, loading, reload: load, setData };
}

// ── shared bits ───────────────────────────────────────────────────────────────────────────────

export function Loading({ what = "loading…" }: { what?: string }) {
  return <div className="loading">{what}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function ErrorBanner({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="banner" role="alert">
      <span className="grow">{error}</span>
      {onRetry && <button onClick={onRetry}>Retry</button>}
    </div>
  );
}

// ── toasts ────────────────────────────────────────────────────────────────────────────────────

const ToastCtx = createContext<(msg: string, err?: boolean) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastHost({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ msg: string; err: boolean } | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const notify = useCallback((msg: string, err = false) => {
    setToast({ msg, err });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(null), 4000);
  }, []);
  return (
    <ToastCtx.Provider value={notify}>
      {children}
      {toast && <div className={`toast${toast.err ? " err" : ""}`} role="status">{toast.msg}</div>}
    </ToastCtx.Provider>
  );
}
