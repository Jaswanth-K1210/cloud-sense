import { useCallback, useEffect, useState, type ReactNode } from "react";
import { memoryParts, type MemoryHit } from "../api";

/** Fetch-on-mount with loading / error / reload. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    fn().then(setData, (e: Error) => setError(e.message)).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(reload, [reload]);
  return { data, error, loading, reload, setData };
}

export function PageState({ loading, error, empty, children, onRetry }: {
  loading: boolean; error: string | null; empty?: ReactNode | false; children: ReactNode; onRetry?: () => void;
}) {
  if (loading) return <p className="py-10 text-muted" role="status">Loading…</p>;
  if (error)
    return (
      <div className="my-6 rounded-md border border-reject/40 p-4" role="alert">
        <p className="font-medium text-reject">Couldn't load this page: {error}</p>
        <p className="mt-1 text-sm text-muted">Check that the API is running and your user is selected in the header.</p>
        {onRetry && <button className="btn mt-3" onClick={onRetry}>Try again</button>}
      </div>
    );
  if (empty) return <div className="py-10 text-muted">{empty}</div>;
  return <>{children}</>;
}

export function PageTitle({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

/** An engineer's words, set as a quote. The visual signature of the app. */
export function Voice({ children, who }: { children: ReactNode; who?: ReactNode }) {
  return (
    <figure>
      <blockquote className="voice">{children}</blockquote>
      {who && <figcaption className="mt-1 text-xs text-muted">{who}</figcaption>}
    </figure>
  );
}

export function MemoryList({ hits, cited = [] }: { hits: MemoryHit[]; cited?: string[] }) {
  if (!hits.length) return <p className="text-sm text-muted">No past decisions matched.</p>;
  return (
    <ul className="space-y-3">
      {hits.map((h) => {
        const p = memoryParts(h.text);
        return (
          <li key={h.id} className={`border-l-2 pl-3 ${cited.includes(h.id) ? "border-learned" : "border-rule"}`}>
            {p.reason ? <Voice who={p.proposal}>{p.reason}</Voice> : <p className="text-sm">{h.text}</p>}
            {cited.includes(h.id) && <p className="mt-1 text-xs font-medium text-learned">Cited by the agent</p>}
          </li>
        );
      })}
    </ul>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title}
        className="w-full max-w-lg rounded-lg border border-rule bg-panel p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-4 text-lg font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  );
}

const STATUS_STYLE: Record<string, string> = {
  pending: "text-ink border-rule", asked: "text-learned border-learned/50", suppressed: "text-learned border-learned/50",
  approved: "text-approve border-approve/50", executed: "text-approve border-approve/50",
  rejected: "text-reject border-reject/50", snoozed: "text-muted border-rule",
};
const STATUS_LABEL: Record<string, string> = {
  pending: "Awaiting review", asked: "Agent unsure", suppressed: "Skipped by agent", approved: "Approved",
  executed: "Executed", rejected: "Rejected", snoozed: "Snoozed",
};

export function StatusTag({ status }: { status: string }) {
  return (
    <span className={`inline-block rounded border px-1.5 py-0.5 text-xs font-medium ${STATUS_STYLE[status] ?? ""}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}
