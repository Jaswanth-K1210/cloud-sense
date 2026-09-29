import { ArrowLeft, Check, GitBranch } from "lucide-react";
import { useState } from "react";
import { api, money, post, type Action, type Candidate } from "../api";
import { Icon } from "../components/Icon";
import { Banner } from "../components/form";
import { Pill, quoteParts, Sparkline, TYPE_LABEL } from "../components/bits";
import { TopBar, useShell } from "../components/Shell";
import { PageState, useLoad } from "../components/ui";
import { describe } from "./Queue";

interface Detail {
  candidate: Candidate;
  resource: { id: string; instance_type?: string; volume_type?: string; created_at?: string; tags: Record<string, string>;
    owner_team?: string; attrs?: Record<string, unknown>; size_gb?: number };
  plan: { kind: string | null; steps: { service: string; op: string; text: string }[]; undo?: string; error?: string;
    terraform_diff?: string };
  actions: (Action & { at?: string; pre_snapshot_ids?: string[] })[];
}

const fmtDate = (iso?: string) => (iso ? new Date(iso).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" }) : "—");

/** Figma 13: execute an approved action (plan → run → undo). */
export default function Execute({ candidateId }: { candidateId: string }) {
  const { org, refresh } = useShell();
  const det = useLoad(() => api<Detail>(`/candidates/${candidateId}`), [candidateId]);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const d = det.data;
  const c = d?.candidate;
  const safety = org?.settings.safety ?? {};
  const dryRun = org?.dry_run ?? true;
  const recommendOnly = (safety.mode ?? "recommend") === "recommend";
  const mustType = Boolean(safety.type_confirm);
  const done = d?.actions.find((a) => a.status === "done");
  const lastRun = d?.actions[0];

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await post<Action>(`/candidates/${candidateId}/execute`);
      det.reload();
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const undo = async (id: string) => {
    setBusy(true);
    try {
      await post(`/actions/${id}/undo`);
      det.reload();
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const mems = c?.agent?.memories ?? [];
  const approvals = mems.filter((m) => m.text.includes("Verdict: APPROVE")).map((m) => quoteParts(m.text));

  return (
    <>
      <a href="#recommendations" className="-mb-2 flex w-fit items-center gap-1 text-sm font-medium text-muted hover:text-ink"><ArrowLeft size={14} /> Recommendations</a>
      <TopBar title={c ? `${describe(c)}: ${c.resource.name}` : "Execute action"}
        subtitle={c ? `${[c.resource.account, c.resource.region].filter(Boolean).join(" · ")} · approved · saves ${money(c.monthly_saving)}/mo` : undefined} />
      <PageState loading={det.loading && !d} error={det.error} onRetry={det.reload}>
        {d && c && (
          <div className="flex flex-wrap items-start gap-6">
            <div className="flex min-w-[320px] flex-1 flex-col gap-5">
              <section className="card flex flex-col gap-4 p-6">
                <h2 className="text-[15px] font-semibold text-ink">Resource</h2>
                <dl className="grid grid-cols-[140px_1fr] gap-x-4 gap-y-3 text-sm">
                  <dt className="text-muted">Type</dt><dd className="text-ink">{TYPE_LABEL[c.resource.type] ?? c.resource.type}{c.resource.instance_type ? ` · ${c.resource.instance_type}` : ""}</dd>
                  <dt className="text-muted">Resource ID</dt><dd className="font-mono text-[13px] text-ink">{c.resource.id}</dd>
                  <dt className="text-muted">Owner</dt><dd className="text-ink">{c.resource.owner_team ? `${c.resource.owner_team} team` : "—"}</dd>
                  <dt className="text-muted">Launched</dt><dd className="text-ink">{fmtDate(c.resource.created_at ?? undefined)}</dd>
                  <dt className="text-muted">Tags</dt><dd className="text-ink">{Object.entries(c.resource.tags).map(([k, v]) => `${k}:${v}`).join(" · ") || "none"}</dd>
                  {Array.isArray(d.resource.attrs?.volumes) && (d.resource.attrs!.volumes as string[]).length > 0 && (
                    <><dt className="text-muted">Attached volumes</dt><dd className="font-mono text-[13px] text-ink">{(d.resource.attrs!.volumes as string[]).join(", ")}</dd></>
                  )}
                </dl>
              </section>
              <section className="card flex flex-col gap-3 p-6">
                <h2 className="text-[15px] font-semibold text-ink">CPU, last 14 days</h2>
                <Sparkline values={c.resource.metrics?.daily_cpu_series} height={90} width={260} />
                <p className="text-[13px] text-muted">{c.signals_text}</p>
              </section>
              {c.blast_radius.count === 0
                ? <Banner kind="ok" title="Blast radius: 0 dependents">Nothing attaches to or routes through this resource.</Banner>
                : <Banner kind="warn" title={`Blast radius: ${c.blast_radius.count} dependent${c.blast_radius.count === 1 ? "" : "s"}`}>{c.blast_radius.names.join(", ")}</Banner>}
              {approvals.length > 0 && (
                <Banner kind="mem" title={`Similar decisions: ${approvals.map((a) => a.proposal).filter(Boolean).slice(0, 2).join(" and ")} ${approvals.length === 1 ? "was" : "were"} approved`}>
                  Approved by {[...new Set(approvals.map((a) => a.who).filter(Boolean))].join(" and ")}{approvals[0].when ? `, ${approvals[0].when}` : ""}.
                </Banner>
              )}
            </div>

            <section className="card flex w-full flex-col gap-5 p-6 lg:w-[480px]">
              <div className="flex items-center gap-2">
                <h2 className="flex-1 text-[17px] font-semibold text-ink">Execution plan</h2>
                {dryRun && <Pill tone="warn" icon={<Icon name="eye" size={12} />}>DRY RUN</Pill>}
              </div>
              {d.plan.error && <Banner kind="warn" title="Not executable">{d.plan.error}</Banner>}
              {d.plan.terraform_diff ? (
                <>
                  <Banner kind="info" icon={<GitBranch size={18} className="text-approve" />} title="Managed by Terraform">CloudSense never changes it directly. Open a pull request with this change:</Banner>
                  <pre className="overflow-x-auto rounded-lg bg-paper p-3 text-xs leading-5 text-ink">{d.plan.terraform_diff}</pre>
                  <button className="btn w-fit" onClick={() => navigator.clipboard?.writeText(d.plan.terraform_diff!)}>Copy Terraform change</button>
                </>
              ) : (
                <ol className="flex flex-col gap-4">
                  {d.plan.steps.map((s, i) => (
                    <li key={i} className="flex gap-3">
                      <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-track text-xs font-semibold text-ink">{i + 1}</span>
                      <div className="flex flex-col gap-1">
                        <p className="text-sm text-ink">{s.text}</p>
                        <code className="w-fit rounded bg-paper px-1.5 py-0.5 text-xs text-muted">{s.service}:{s.op}</code>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
              <dl className="grid grid-cols-2 gap-4 rounded-lg bg-paper p-4 text-sm">
                <div><dt className="text-xs text-muted">Estimated saving</dt><dd className="font-semibold text-ink">{money(c.monthly_saving)}/mo</dd></div>
                <div><dt className="text-xs text-muted">Undo</dt><dd className="text-ink">{d.plan.undo || "—"}</dd></div>
              </dl>

              {!d.plan.terraform_diff && !d.plan.error && !done && c.status === "approved" && (
                recommendOnly ? (
                  <Banner kind="info" title="Recommend-only mode">Nothing runs in AWS. <a href="#settings/safety" className="font-semibold text-approve">Switch to Safe actions</a> to execute.</Banner>
                ) : (
                  <>
                    {mustType && !dryRun && (
                      <label className="flex flex-col gap-1.5">
                        <span className="text-[13px] font-medium text-ink">Type <b>{c.resource.name}</b> to confirm</span>
                        <input value={typed} onChange={(e) => setTyped(e.target.value)} className="h-[39px] rounded-lg border border-rule px-3 text-sm" placeholder={c.resource.name} />
                      </label>
                    )}
                    <div className="flex gap-2">
                      <button className="btn btn-approve h-[35px] flex-1" onClick={run}
                        disabled={busy || (mustType && !dryRun && typed !== c.resource.name)}>
                        {busy ? "Running…" : dryRun ? "Run dry run" : "Run for real"}
                      </button>
                      <a href="#recommendations" className="btn h-[37px]">Cancel</a>
                    </div>
                    {dryRun && <p className="text-xs text-muted">Dry run is on: this shows the calls without changing anything. Turn it off in <a href="#settings/safety" className="text-approve">Settings → Safety</a> to run for real.</p>}
                  </>
                )
              )}
              {error && <Banner kind="err" title={error} />}

              {lastRun && (
                <>
                  <div className="h-px bg-rule" />
                  <p className="text-[11px] font-semibold tracking-[0.8px] text-muted">{lastRun.status === "dry_run" ? "DRY RUN RESULT" : "AFTER RUN"}</p>
                  <ul className="flex flex-col gap-2.5">
                    {lastRun.api_calls.map((a, i) => (
                      <li key={i} className="flex items-center gap-2 text-sm">
                        <span className={`flex size-5 items-center justify-center rounded-full ${lastRun.status === "done" ? "bg-success text-white" : "bg-track text-muted"}`}><Check size={12} /></span>
                        <span className="flex-1 text-ink">{d.plan.steps[i]?.text ?? a.op}</span>
                        <code className="text-xs text-muted">{a.op}</code>
                      </li>
                    ))}
                  </ul>
                  {lastRun.status === "done" && (
                    <div className="flex items-center gap-3">
                      <div className="flex-1"><Banner kind="ok" title="Done. Saving starts now." /></div>
                      <button className="btn h-[31px]" disabled={busy} onClick={() => undo(lastRun.id)}>Undo</button>
                    </div>
                  )}
                  {lastRun.status === "undone" && <Banner kind="info" title="Undone">The resource was restored; the recommendation is approved again.</Banner>}
                  {lastRun.status === "dry_run" && <Banner kind="warn" title="Dry run only: nothing changed in AWS" />}
                </>
              )}
            </section>
          </div>
        )}
      </PageState>
    </>
  );
}
