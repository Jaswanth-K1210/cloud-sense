import { useEffect, useState } from "react";
import { api, money, ORG, post, type Action, type Candidate, type MemoryHit, type ScanDetail, type ScanSummary,
  type Verdict } from "../api";
import { useShell } from "../components/Shell";
import { MemoryList, Modal, PageState, PageTitle, StatusTag, useLoad, Voice } from "../components/ui";

export const ACTION: Record<string, string> = {
  stop: "Stop", rightsize: "Rightsize", snapshot_delete: "Snapshot, then delete", modify_gp3: "Change gp2 to gp3",
  release: "Release", delete_snapshot: "Delete snapshot", s3_lifecycle: "Add a lifecycle rule",
};

async function latestScan(): Promise<ScanDetail | null> {
  const scans = await api<ScanSummary[]>(`/orgs/${ORG}/scans`);
  return scans.length ? api<ScanDetail>(`/orgs/${ORG}/scans/${scans[0].id}`) : null;
}

export default function Queue() {
  const shell = useShell();
  const scan = useLoad(latestScan, [shell.lastScan?.id, shell.lastScan?.status]);
  const [rejecting, setRejecting] = useState<Candidate | null>(null);
  const [why, setWhy] = useState<Candidate | null>(null);
  const [learning, setLearning] = useState<Record<string, Verdict>>({});
  const [flash, setFlash] = useState<string | null>(null);

  // A scan runs in the background: poll until it finishes.
  useEffect(() => {
    if (scan.data?.status !== "running") return;
    const t = setTimeout(scan.reload, 2000);
    return () => clearTimeout(t);
  }, [scan.data, scan.reload]);

  // Poll verdicts that are still consolidating.
  useEffect(() => {
    const pending = Object.values(learning).filter((v) => v.learning_status === "learning");
    if (!pending.length) return;
    const t = setTimeout(async () => {
      const updated = await Promise.all(pending.map((v) => api<Verdict>(`/verdicts/${v.id}`).catch(() => v)));
      setLearning((cur) => ({ ...cur, ...Object.fromEntries(updated.map((v) => [v.id, v])) }));
    }, 2000);
    return () => clearTimeout(t);
  }, [learning]);

  const verdict = async (c: Candidate, body: Record<string, unknown>) => {
    try {
      const v = await post<Verdict>(`/candidates/${c.id}/verdict`, body);
      if (v.decision === "reject") setLearning((cur) => ({ ...cur, [v.id]: v }));
      setFlash(null);
      scan.reload();
    } catch (e) {
      setFlash((e as Error).message);
    }
  };

  const d = scan.data;
  const toReview = d ? [...d.recommended, ...d.asked].sort((a, b) => (b.monthly_saving ?? 0) - (a.monthly_saving ?? 0)) : [];
  const approved = d ? d.reviewed.filter((c) => c.status === "approved" || c.status === "executed") : [];

  return (
    <>
      <PageTitle title="Recommendations"
        subtitle={d ? `${toReview.length} open · ${money(toReview.reduce((n, c) => n + (c.monthly_saving ?? 0), 0))}/mo potential · sorted by saving` : undefined} />
      {Object.values(learning).map((v) => <LearningBanner key={v.id} v={v} />)}
      {flash && <p className="mb-4 rounded-md border border-reject/40 p-3 text-sm text-reject" role="alert">{flash}</p>}

      <PageState loading={scan.loading && !d} error={scan.error} onRetry={scan.reload}
        empty={!d && "No scans yet. Connect an account in Settings, then run a scan."}>
        {d?.status === "running" && <p className="mb-4 text-muted" role="status">Scanning your account…</p>}
        {d?.status === "failed" && <p className="mb-4 text-reject">The scan failed: {JSON.stringify(d.errors)}</p>}
        {d && d.errors.length > 0 && d.status === "done" && (
          <p className="mb-4 text-sm text-learned">Finished with warnings: {d.errors.map((e) => Object.values(e).join(": ")).join("; ")}</p>
        )}

        {d && d.status !== "running" && (
          <>
            <h2 className="mb-3 font-semibold">{toReview.length ? `${toReview.length} waiting for a decision` : "Nothing waiting for a decision"}</h2>
            <ul className="space-y-3">
              {toReview.map((c) => (
                <CandidateCard key={c.id} c={c}>
                  <button className="btn btn-approve" onClick={() => verdict(c, { decision: "approve" })}>Approve</button>
                  <button className="btn btn-reject" onClick={() => setRejecting(c)}>Reject</button>
                  <button className="btn" onClick={() => verdict(c, { decision: "snooze" })}>Snooze 30 days</button>
                  <button className="btn" onClick={() => setWhy(c)}>Why?</button>
                </CandidateCard>
              ))}
            </ul>

            <details className="mt-8 rounded-lg border border-rule bg-panel p-4">
              <summary className="cursor-pointer font-semibold">Skipped by the agent ({d.suppressed.length})</summary>
              <p className="mt-1 text-sm text-muted">Recommendations it held back because of a hard rule or something your team taught it.</p>
              <ul className="mt-4 space-y-5">
                {d.suppressed.map((c) => (
                  <li key={c.id} className="border-t border-rule pt-4">
                    <p className="font-medium">{ACTION[c.action] ?? c.action} {c.resource.name}
                      <span className="ml-2 text-sm font-normal text-muted">{money(c.monthly_saving)}/month not pursued</span></p>
                    <p className="mt-1 text-sm">{c.agent.reason}</p>
                    {(c.agent.memories?.length ?? 0) > 0 && (
                      <div className="mt-3"><MemoryList hits={c.agent.memories as MemoryHit[]} cited={c.agent.cited_memory_ids} /></div>
                    )}
                  </li>
                ))}
              </ul>
            </details>

            {approved.length > 0 && <Approved items={approved} onChange={scan.reload} />}
          </>
        )}
      </PageState>

      {rejecting && <RejectModal c={rejecting} onClose={() => setRejecting(null)}
        onSubmit={(body) => { verdict(rejecting, body); setRejecting(null); }} />}
      {why && <WhyModal c={why} onClose={() => setWhy(null)} />}
    </>
  );
}

function CandidateCard({ c, children }: { c: Candidate; children: React.ReactNode }) {
  return (
    <li className="rounded-lg border border-rule bg-panel p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-lg font-semibold">{ACTION[c.action] ?? c.action} {c.resource.name}</p>
        <p className="text-lg font-semibold tabular-nums">{money(c.monthly_saving)}<span className="text-sm font-normal text-muted">/month</span></p>
      </div>
      <p className="text-sm text-muted">{c.resource.type} {c.resource.id} in {c.resource.region}{c.resource.owner_team ? `, owned by ${c.resource.owner_team}` : ""}</p>
      <p className="mt-2 text-sm">{c.signals_text}</p>
      <p className="mt-1 text-sm">
        {c.blast_radius.count ? `Affects ${c.blast_radius.count} other resource${c.blast_radius.count > 1 ? "s" : ""}: ${c.blast_radius.names.slice(0, 5).join(", ")}` : "Nothing depends on it."}
        {c.resource.iac_managed && " Managed by Terraform: CloudSense will produce a diff instead of changing it."}
      </p>
      {(c.warnings?.length ?? 0) > 0 && <p className="mt-1 text-sm text-learned">{c.warnings!.join(". ")}</p>}
      {c.status === "asked" && <p className="mt-2 text-sm"><StatusTag status="asked" /> {c.agent.reason}</p>}
      {(c.agent.memories?.length ?? 0) > 0 && (
        <details className="mt-2 text-sm"><summary className="cursor-pointer text-muted">Past decisions it checked ({c.agent.memories!.length})</summary>
          <div className="mt-2"><MemoryList hits={c.agent.memories!} cited={c.agent.cited_memory_ids} /></div></details>
      )}
      <div className="mt-3 flex flex-wrap gap-2">{children}</div>
    </li>
  );
}

function LearningBanner({ v }: { v: Verdict }) {
  const text = v.learning_status === "learning" ? "Saved. Learning from your reason…"
    : v.learning_status === "learned" ? "Rule learned" : v.learning_status === "timeout"
      ? "Saved. Still consolidating; the rule will appear under Learned rules shortly." : "Saved, but memory is unavailable right now.";
  return (
    <div className="mb-4 rounded-lg border border-learned/50 bg-panel p-4" role="status">
      <p className="text-sm font-medium text-learned">{text}</p>
      {v.learned_rule ? <div className="mt-2"><Voice who={`Confirmed ${v.learned_rule.proof_count}×`}>{v.learned_rule.text}</Voice></div>
        : <div className="mt-2"><Voice>{v.reason}</Voice></div>}
    </div>
  );
}

export function RejectModal({ c, onClose, onSubmit }: { c: Candidate; onClose: () => void; onSubmit: (b: Record<string, unknown>) => void }) {
  const [reason, setReason] = useState("");
  const [scope, setScope] = useState("this_resource");
  const [until, setUntil] = useState("");
  return (
    <Modal title={`Reject: ${ACTION[c.action] ?? c.action} ${c.resource.name}`} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); if (reason.trim()) onSubmit({ decision: "reject", reason, scope, until_date: until ? `${until}T00:00:00Z` : null }); }}>
        <label className="block text-sm font-medium" htmlFor="reason">Why should CloudSense leave it alone?</label>
        <p className="mb-2 text-xs text-muted">Your reason becomes a rule it applies to similar resources.</p>
        <textarea id="reason" className="field font-voice italic" rows={3} required autoFocus value={reason}
          placeholder="DR standby for orders-db, idle on purpose" onChange={(e) => setReason(e.target.value)} />
        <fieldset className="mt-4">
          <legend className="text-sm font-medium">Applies to</legend>
          {[["this_resource", "Only this resource"], ["similar", "All similar resources"], ["team", "Everything this team owns"]].map(([v, l]) => (
            <label key={v} className="mt-1 flex items-center gap-2 text-sm">
              <input type="radio" name="scope" value={v} checked={scope === v} onChange={() => setScope(v)} /> {l}
            </label>
          ))}
        </fieldset>
        <label className="mt-4 block text-sm font-medium" htmlFor="until">Temporary? Leave it alone until (optional)</label>
        <input id="until" type="date" className="field mt-1" value={until} onChange={(e) => setUntil(e.target.value)} />
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn border-reject bg-reject text-white" disabled={!reason.trim()}>Reject and teach</button>
        </div>
      </form>
    </Modal>
  );
}

function WhyModal({ c, onClose }: { c: Candidate; onClose: () => void }) {
  const ans = useLoad(() => post<{ text: string; based_on: MemoryHit[] }>(`/candidates/${c.id}/why`), [c.id]);
  return (
    <Modal title={`Why ${ACTION[c.action]?.toLowerCase() ?? c.action} ${c.resource.name}?`} onClose={onClose}>
      <p className="text-sm"><span className="font-medium">Agent:</span> {c.agent.reason}</p>
      <div className="mt-4">
        <PageState loading={ans.loading} error={ans.error} onRetry={ans.reload}>
          <p className="whitespace-pre-wrap text-sm">{ans.data?.text}</p>
          <h3 className="mb-2 mt-4 text-sm font-semibold">Sources</h3>
          <MemoryList hits={ans.data?.based_on ?? []} />
        </PageState>
      </div>
      <div className="mt-5 flex justify-end"><button className="btn" onClick={onClose}>Close</button></div>
    </Modal>
  );
}

function Approved({ items, onChange }: { items: Candidate[]; onChange: () => void }) {
  const { org } = useShell();
  const safety = org?.settings.safety ?? {};
  const recommendOnly = (safety.mode ?? "recommend") === "recommend";
  const mustType = Boolean(safety.type_confirm) && org?.dry_run === false;
  const [typing, setTyping] = useState<Record<string, string>>({});
  const [result, setResult] = useState<Record<string, Action | string>>({});
  const run = async (c: Candidate) => {
    try {
      const a = await post<Action>(`/candidates/${c.id}/execute`);
      setResult((r) => ({ ...r, [c.id]: a }));
      onChange();
    } catch (e) {
      setResult((r) => ({ ...r, [c.id]: (e as Error).message }));
    }
  };
  const undo = async (c: Candidate, a: Action) => {
    try {
      setResult((r) => ({ ...r, [c.id]: `Undone (${a.kind})` }));
      await post(`/actions/${a.id}/undo`);
      onChange();
    } catch (e) {
      setResult((r) => ({ ...r, [c.id]: (e as Error).message }));
    }
  };
  return (
    <section className="mt-8">
      <h2 className="mb-3 font-semibold">Approved</h2>
      <ul className="space-y-2">
        {items.map((c) => {
          const r = result[c.id];
          return (
            <li key={c.id} className="rounded-lg border border-rule bg-panel p-3">
              <div className="flex flex-wrap items-center gap-3">
                <StatusTag status={c.status} />
                <span className="font-medium">{ACTION[c.action] ?? c.action} {c.resource.name}</span>
                <span className="text-sm text-muted">{money(c.monthly_saving)}/month</span>
                {c.status === "approved" && (recommendOnly
                  ? <span className="ml-auto text-xs text-muted">Recommend-only mode: <a href="#settings/safety" className="font-medium text-approve">enable safe actions</a> to execute</span>
                  : mustType && typing[c.id] !== undefined ? (
                    <span className="ml-auto flex items-center gap-2">
                      <input aria-label={`Type ${c.resource.name} to confirm`} autoFocus placeholder={`Type ${c.resource.name}`}
                        className="h-8 rounded-lg border border-rule px-2 text-[13px]" value={typing[c.id]}
                        onChange={(e) => setTyping((t) => ({ ...t, [c.id]: e.target.value }))} />
                      <button className="btn btn-reject" disabled={typing[c.id] !== c.resource.name} onClick={() => run(c)}>Run for real</button>
                    </span>
                  ) : (
                    <button className="btn ml-auto" onClick={() => (mustType ? setTyping((t) => ({ ...t, [c.id]: "" })) : run(c))}>
                      {org?.dry_run ? "Execute (dry run)" : "Execute"}
                    </button>
                  ))}
              </div>
              {typeof r === "string" && <p className="mt-2 text-sm text-reject">{r}</p>}
              {r && typeof r !== "string" && (
                <div className="mt-2 text-sm">
                  <p>{r.status === "dry_run" ? "Dry run. These calls would be made:" : r.status === "diff" ? "Managed by Terraform. Open a pull request with:" : "Done. Calls made:"}</p>
                  {r.status === "diff"
                    ? <pre className="mt-1 overflow-x-auto rounded bg-paper p-2 text-xs">{String(r.undo_handle.terraform_diff)}</pre>
                    : <ol className="mt-1 list-decimal pl-5 text-muted">{r.api_calls.map((a, i) => <li key={i}>{a.service}:{a.op}</li>)}</ol>}
                  {r.status === "done" && <button className="btn mt-2" onClick={() => undo(c, r)}>Undo</button>}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
