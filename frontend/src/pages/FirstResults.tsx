import { ArrowRight, Database, HardDrive, Server, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { api, money, ORG, post, type Candidate, type ScanDetail } from "../api";
import { Icon } from "../components/Icon";
import { Banner } from "../components/form";
import { useLoad } from "../components/ui";
import { describe, RejectModal } from "./Queue";

const TYPE_ICON: Record<string, LucideIcon> = { ec2: Server, rds: Database, ebs: HardDrive, snapshot: HardDrive, s3: Database };


/** Figma 10: shown once, right after the first scan. */
export default function FirstResults({ scanId }: { scanId: string }) {
  const scan = useLoad(() => api<ScanDetail>(`/orgs/${ORG}/scans/${scanId}`), [scanId]);
  const [rejecting, setRejecting] = useState<Candidate | null>(null);
  const [done, setDone] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const verdict = async (c: Candidate, body: Record<string, unknown>) => {
    try {
      await post(`/candidates/${c.id}/verdict`, body);
      setDone((d) => ({ ...d, [c.id]: body.decision === "approve" ? "Approved" : "Rejected · learning" }));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const d = scan.data;
  if (scan.loading && !d) return <p className="py-10 text-muted" role="status">Loading your results…</p>;
  if (!d) return <Banner kind="err" title={`Couldn't load the scan: ${scan.error}`} />;
  const open = [...d.recommended, ...d.asked];
  const total = open.reduce((n, c) => n + (c.monthly_saving ?? 0), 0);
  const top = [...open].sort((a, b) => (b.monthly_saving ?? 0) - (a.monthly_saving ?? 0)).slice(0, 5);

  return (
    <div className="flex flex-col gap-6 pt-2">
      <section className="flex flex-col gap-3 rounded-2xl bg-side-bg px-10 py-9 text-white">
        <p className="text-xs font-semibold tracking-[0.8px] text-side-text">POTENTIAL SAVINGS FOUND</p>
        <p className="flex items-baseline gap-2">
          <span className="text-[56px] font-bold leading-none tracking-[-1.5px]">{money(total)}</span>
          <span className="text-xl text-side-soft">/ month</span>
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          <span className="flex items-center gap-1.5 rounded-full bg-side-raised px-3 py-1 text-sm"><Icon name="inbox" size={12} className="text-side-active" /> {open.length} recommendation{open.length === 1 ? "" : "s"}</span>
          <span className="flex items-center gap-1.5 rounded-full bg-side-raised px-3 py-1 text-sm"><Icon name="sparkles" size={12} className="text-side-memory" /> {d.suppressed.length} skipped by your rules</span>
          <span className="flex items-center gap-1.5 rounded-full bg-side-raised px-3 py-1 text-sm"><Icon name="alert" size={12} className="text-warn-soft" /> {d.asked.length} need your input</span>
        </div>
      </section>
      {error && <Banner kind="err" title={error} />}
      <div className="flex flex-wrap items-start gap-6">
        <section className="card min-w-0 flex-1">
          <div className="flex items-center px-6 py-4">
            <h2 className="text-base font-semibold text-ink">Top {top.length} by saving</h2>
            <span className="flex-1" />
            <a href="#recommendations" className="flex items-center gap-1 text-sm font-semibold text-approve">View all {open.length} <ArrowRight size={14} /></a>
          </div>
          {top.length === 0 && <p className="border-t border-rule px-6 py-8 text-sm text-muted">Nothing to fix. Your account looks clean.</p>}
          <ul>
            {top.map((c) => {
              const I = TYPE_ICON[c.resource.type] ?? Server;
              return (
                <li key={c.id} className="flex flex-wrap items-center gap-4 border-t border-rule px-6 py-4">
                  <span className="flex size-9 items-center justify-center rounded-lg bg-track text-muted"><I size={18} /></span>
                  <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <p className="truncate text-sm font-semibold text-ink">{c.resource.name}</p>
                    <p className="text-[13px] text-muted">{describe(c)}</p>
                  </div>
                  <span className="text-[15px] font-semibold text-ink">{money(c.monthly_saving)}/mo</span>
                  {done[c.id] ? <span className="w-[155px] text-right text-sm font-medium text-muted">{done[c.id]}</span> : (
                    <span className="flex gap-2">
                      <button className="btn btn-approve h-[29px]" onClick={() => verdict(c, { decision: "approve" })}>Approve</button>
                      <button className="btn btn-reject h-[29px]" onClick={() => setRejecting(c)}>Reject</button>
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
        <aside className="flex w-full flex-col gap-4 lg:w-[340px]">
          <div className="card flex flex-col gap-3 p-6">
            <span className="flex size-10 items-center justify-center rounded-full bg-learned-soft text-learned"><Icon name="sparkles" size={22} /></span>
            <p className="text-base font-semibold leading-snug text-ink">Reject anything that’s wrong, and tell us why in one sentence.</p>
            <p className="text-sm leading-[1.5] text-muted">CloudSense won’t make that mistake again, on this resource or any look-alike.</p>
          </div>
          <a href="#recommendations" className="btn btn-approve h-[35px]">Review all recommendations</a>
          <a href="#map" className="btn h-[37px]">See resource map</a>
        </aside>
      </div>
      {rejecting && <RejectModal c={rejecting} onClose={() => setRejecting(null)}
        onSubmit={(body) => { verdict(rejecting, body); setRejecting(null); }} />}
    </div>
  );
}
