import { Check, Lock, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ORG, type ScanDetail, type ScanSummary } from "../api";
import { Icon } from "../components/Icon";
import { Banner } from "../components/form";
import { useShell } from "../components/Shell";

const TYPE: Record<string, string> = { ec2: "EC2", ebs: "EBS", rds: "RDS", s3: "S3", eip: "Elastic IPs",
  snapshot: "Snapshots", lb: "Load balancers", nat: "NAT", eks: "EKS", opensearch: "OpenSearch" };
const POLL_MS = 1000;

/** Figma 09: live progress while a scan runs. */
export default function ScanProgress({ scanId }: { scanId: string }) {
  const shell = useShell();
  const [scan, setScan] = useState<ScanDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const s = await api<ScanDetail>(`/orgs/${ORG}/scans/${scanId}`);
        if (!alive) return;
        setScan(s);
        if (s.status === "done") {
          const all = await api<ScanSummary[]>(`/orgs/${ORG}/scans`);
          shell.refresh();
          // The first-results ("aha") screen is shown once, after the very first scan.
          window.location.hash = all.length === 1 ? `results/${scanId}` : "recommendations";
          return;
        }
        if (s.status === "running") setTimeout(tick, POLL_MS);
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
    };
    tick();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanId]);

  const p = scan?.progress ?? {};
  const step = Math.min(p.step ?? 1, 7);
  const counts = Object.entries(p.counts ?? {}).filter(([t]) => TYPE[t]);
  const found = counts.reduce((n, [, c]) => n + c, 0);
  const steps = [
    `Connecting to ${p.account ?? "your account"}`,
    found ? `Discovering resources: ${found} found` : "Discovering resources",
    "Reading 14 days of usage metrics",
    "Mapping dependencies",
    "Finding savings",
    "Checking your rules and memory",
  ];
  // discovery and the metrics read finish together; show step 3 as done once step 4 starts
  const shown = step === 2 ? 3 : step;

  return (
    <div className="flex flex-col gap-5 pt-6">
      {error && <Banner kind="err" title={`Couldn't read the scan: ${error}`} />}
      {scan?.status === "failed" && (
        <Banner kind="err" title="The scan failed">
          {scan.errors.map((e) => Object.values(e).join(": ")).join("; ")} <a href="#settings" className="font-semibold underline">Check your account connection</a>
        </Banner>
      )}
      <div className="flex flex-wrap items-start justify-center gap-6">
        <section className="card flex w-full max-w-[744px] flex-col gap-6 p-8" aria-live="polite">
          <div className="flex items-start gap-4">
            <div className="flex flex-1 flex-col gap-1">
              <h1 className="text-[22px] font-bold tracking-[-0.3px] text-ink">Scanning {p.account ?? "your account"}…</h1>
              <p className="text-sm text-muted">Step {Math.min(shown, 6)} of 6 · usually about a minute</p>
            </div>
            <span className="flex items-center gap-1 rounded-full bg-track px-2.5 py-1 text-xs font-medium text-ink"><Lock size={12} /> Read-only</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-track">
            <div className="h-full rounded-full bg-approve transition-all duration-500" style={{ width: `${(Math.min(shown - 1, 6) / 6) * 100}%` }} />
          </div>
          <ol className="flex flex-col gap-4">
            {steps.map((label, i) => {
              const n = i + 1, done = n < shown, active = n === shown;
              return (
                <li key={i} className="flex items-center gap-3">
                  <span className={`flex size-6 items-center justify-center rounded-full ${done ? "bg-approve text-white" : active ? "bg-approve/10 text-approve" : "bg-track text-muted"}`}>
                    {done ? <Check size={14} strokeWidth={3} /> : active ? <RefreshCw size={14} className="animate-spin" /> : <span className="size-1.5 rounded-full bg-muted/50" />}
                  </span>
                  <span className={`text-[15px] ${done || active ? "font-medium text-ink" : "text-muted"}`}>{label}</span>
                </li>
              );
            })}
          </ol>
          {counts.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {counts.map(([t, n]) => (
                <span key={t} className="rounded-full bg-paper px-2.5 py-1 text-[13px] font-medium text-ink">{TYPE[t]} · {n}</span>
              ))}
            </div>
          )}
        </section>
        <aside className="card flex w-full max-w-[360px] flex-col gap-4 p-6">
          <p className="flex items-center gap-2 text-[15px] font-semibold text-ink"><Icon name="sparkles" size={16} className="text-learned" /> While you wait: how learning works</p>
          <p className="text-sm leading-[1.5] text-ink">1. We flag likely waste, with the evidence and blast radius.</p>
          <p className="text-sm leading-[1.5] text-ink">2. Your team approves or rejects. A rejection needs one sentence of why.</p>
          <p className="text-sm leading-[1.5] text-ink">3. Every “no” becomes a rule, so look-alike resources are skipped next time, with the reason shown.</p>
        </aside>
      </div>
      <p className="text-center text-[13px] text-muted">Existing data stays visible during later scans. Large accounts can take a few minutes.</p>
    </div>
  );
}
