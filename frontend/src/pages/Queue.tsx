import { GitBranch, Lock, Search, X, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, money, ORG, post, type Candidate, type MemoryHit, type ScanDetail, type ScanSummary, type Verdict } from "../api";
import { Icon } from "../components/Icon";
import { Banner } from "../components/form";
import { FilterSelect, Pill, quoteParts, Sparkline, Tabs, TagPills, TypeIcon } from "../components/bits";
import { TopBar, useShell } from "../components/Shell";
import { MemoryList, Modal, PageState, useLoad } from "../components/ui";

export const ACTION: Record<string, string> = {
  stop: "Stop", rightsize: "Rightsize", snapshot_delete: "Snapshot, then delete", modify_gp3: "Change gp2 to gp3",
  release: "Release", delete_snapshot: "Delete snapshot", s3_lifecycle: "Add a lifecycle rule",
};

/** Figma action pill wording. */
export function describe(c: Candidate): string {
  const proposed = c.signals_text.match(/proposed (\S+)/)?.[1];
  if (c.action === "rightsize" && proposed) return `Rightsize to ${proposed}`;
  if (c.action === "stop") return "Stop (snapshot first)";
  if (c.action === "snapshot_delete") return "Delete after snapshot";
  if (c.action === "modify_gp3") return "Switch gp2 → gp3";
  return ACTION[c.action] ?? c.action;
}

function memoryLine(c: Candidate): string {
  const mems = c.agent?.memories ?? [];
  const cited = mems.find((m) => c.agent.cited_memory_ids?.includes(m.id));
  if (!cited) {
    return mems.length ? `Memory checked: ${mems.length} past decision${mems.length === 1 ? "" : "s"}, none apply here`
      : "Memory checked: no past decisions about this pattern";
  }
  const q = quoteParts(cited.text);
  if (q.proposal && q.who) return `Memory: ${q.who} ${cited.text.includes("Verdict: REJECT") ? "rejected" : "approved"} ${q.proposal}${q.when ? ` (${q.when})` : ""}`;
  return `Memory: ${cited.text.split("\n")[0].slice(0, 90)}`;
}

async function latestScan(): Promise<ScanDetail | null> {
  const scans = await api<ScanSummary[]>(`/orgs/${ORG}/scans`);
  const done = scans.find((s) => s.status !== "running") ?? scans[0];
  return done ? api<ScanDetail>(`/orgs/${ORG}/scans/${done.id}`) : null;
}

type TabKey = "review" | "input" | "skipped" | "approved" | "done" | "rejected";

export default function Queue() {
  const shell = useShell();
  const scan = useLoad(latestScan, [shell.lastScan?.id, shell.lastScan?.status]);
  const [tab, setTab] = useState<TabKey>("review");
  const [q, setQ] = useState("");
  const [account, setAccount] = useState("all");
  const [service, setService] = useState("all");
  const [team, setTeam] = useState("all");
  const [minSaving, setMinSaving] = useState("0");
  const [sort, setSort] = useState("saving");
  const [rejecting, setRejecting] = useState<Candidate | null>(null);
  const [why, setWhy] = useState<Candidate | null>(null);
  const [learning, setLearning] = useState<Record<string, Verdict>>({});
  const [flash, setFlash] = useState<string | null>(null);

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
      shell.refresh();
    } catch (e) {
      setFlash((e as Error).message);
    }
  };
  const override = async (c: Candidate) => {
    try {
      await post(`/candidates/${c.id}/override`);
      scan.reload();
      shell.refresh();
    } catch (e) {
      setFlash((e as Error).message);
    }
  };

  const d = scan.data;
  const all = useMemo(() => (d ? [...d.recommended, ...d.asked, ...d.suppressed, ...d.reviewed] : []), [d]);
  const opt = (f: (c: Candidate) => string | null | undefined) =>
    [...new Set(all.map(f).filter(Boolean) as string[])].sort().map((v) => [v, v] as [string, string]);
  const filtered = (list: Candidate[]) => list
    .filter((c) => !q || `${c.resource.name} ${c.resource.id}`.toLowerCase().includes(q.toLowerCase()))
    .filter((c) => account === "all" || c.resource.account === account)
    .filter((c) => service === "all" || c.resource.type === service)
    .filter((c) => team === "all" || c.resource.owner_team === team)
    .filter((c) => (c.monthly_saving ?? 0) >= Number(minSaving))
    .sort((a, b) => (sort === "saving" ? (b.monthly_saving ?? 0) - (a.monthly_saving ?? 0) : a.resource.name.localeCompare(b.resource.name)));
  const by = (st: string[]) => filtered(all.filter((c) => st.includes(c.status)));
  const lists = { review: by(["pending"]), input: by(["asked"]), skipped: by(["suppressed"]), approved: by(["approved"]),
    done: by(["executed"]), rejected: by(["rejected", "snoozed"]) };
  const open = d ? [...d.recommended, ...d.asked] : [];

  return (
    <>
      <TopBar title="Recommendations"
        subtitle={d ? `${open.length} open · ${money(open.reduce((n, c) => n + (c.monthly_saving ?? 0), 0))}/mo potential · sorted by ${sort === "saving" ? "saving" : "name"}` : undefined} />
      {Object.values(learning).map((v) => <LearningBanner key={v.id} v={v} />)}
      {flash && <Banner kind="err" title={flash} />}
      <PageState loading={scan.loading && !d} error={scan.error} onRetry={scan.reload}
        empty={!d && "No scans yet. Click Scan now to find savings in your connected accounts."}>
        {d && (
          <>
            {d.status === "running" && <Banner kind="info" title="A scan is running">Results below are from the previous scan until it finishes.</Banner>}
            <Tabs active={tab} onChange={(k) => setTab(k as TabKey)} tabs={[["review", `Needs review (${lists.review.length})`],
              ["input", `Needs your input (${lists.input.length})`], ["skipped", `Skipped (${lists.skipped.length})`],
              ["approved", `Approved (${lists.approved.length})`], ["done", `Done (${lists.done.length})`], ["rejected", `Rejected (${lists.rejected.length})`]]} />
            <div className="flex flex-wrap items-center gap-2.5">
              <label className="relative flex h-[39px] w-60 items-center">
                <Search size={16} className="absolute left-3 text-muted" />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search resources" aria-label="Search resources"
                  className="h-full w-full rounded-lg border border-rule bg-panel pl-9 pr-3 text-sm focus:border-approve focus:outline-none" />
              </label>
              <FilterSelect label="Account" value={account} onChange={setAccount} options={[["all", "Account: All"], ...opt((c) => c.resource.account)]} />
              <FilterSelect label="Service" value={service} onChange={setService} options={[["all", "Service: All"], ...opt((c) => c.resource.type).map(([v]) => [v, v.toUpperCase()] as [string, string])]} />
              <FilterSelect label="Team" value={team} onChange={setTeam} options={[["all", "Team: All"], ...opt((c) => c.resource.owner_team)]} />
              <FilterSelect label="Minimum saving" value={minSaving} onChange={setMinSaving} options={[["0", "Min saving"], ["10", "$10+/mo"], ["50", "$50+/mo"], ["100", "$100+/mo"]]} />
              <span className="flex-1" />
              <FilterSelect label="Sort" value={sort} onChange={setSort} options={[["saving", "Sort: Highest saving"], ["name", "Sort: Name"]]} />
            </div>

            {tab === "review" && (
              <>
                <CardList items={lists.review} empty="Nothing waiting for review. New recommendations appear after each scan."
                  render={(c) => <RecCard key={c.id} c={c} onApprove={() => verdict(c, { decision: "approve" })}
                    onReject={() => setRejecting(c)} onSnooze={() => verdict(c, { decision: "snooze" })} onWhy={() => setWhy(c)} />} />
                {lists.input.length > 0 && (
                  <>
                    <h2 className="mt-2 flex items-center gap-2 text-[15px] font-semibold text-ink"><Icon name="alert" size={16} className="text-warn" /> Needs your input ({lists.input.length})</h2>
                    {lists.input.map((c) => <AskCard key={c.id} c={c} onApprove={() => verdict(c, { decision: "approve" })} onReject={() => setRejecting(c)} />)}
                  </>
                )}
                {lists.skipped.length > 0 && (
                  <>
                    <div className="mt-2 flex flex-wrap items-baseline gap-3">
                      <h2 className="flex items-center gap-2 text-[15px] font-semibold text-ink"><Icon name="sparkles" size={16} className="text-learned" /> Skipped by CloudSense ({lists.skipped.length})</h2>
                      <p className="text-[13px] text-muted">Not sent to Slack. Each one shows why.</p>
                    </div>
                    {lists.skipped.map((c) => <SkipCard key={c.id} c={c} onOverride={() => override(c)} />)}
                  </>
                )}
              </>
            )}
            {tab === "input" && <CardList items={lists.input} empty="CloudSense isn’t unsure about anything right now."
              render={(c) => <AskCard key={c.id} c={c} onApprove={() => verdict(c, { decision: "approve" })} onReject={() => setRejecting(c)} />} />}
            {tab === "skipped" && <CardList items={lists.skipped} empty="Nothing skipped yet. When your team rejects something with a reason, look-alikes show up here."
              render={(c) => <SkipCard key={c.id} c={c} onOverride={() => override(c)} />} />}
            {tab === "approved" && <CardList items={lists.approved} empty="No approved recommendations waiting to run."
              render={(c) => <RecCard key={c.id} c={c} done={<a href={`#execute/${c.id}`} className="btn btn-approve h-[29px]">Execute</a>} />} />}
            {tab === "done" && <CardList items={lists.done} empty="Nothing executed yet."
              render={(c) => <RecCard key={c.id} c={c} done={<a href={`#execute/${c.id}`} className="btn h-[29px]">View · Undo</a>} />} />}
            {tab === "rejected" && <CardList items={lists.rejected} empty="Nothing rejected or snoozed."
              render={(c) => <RecCard key={c.id} c={c} done={<Pill tone={c.status === "snoozed" ? "plain" : "reject"}>{c.status === "snoozed" ? "Snoozed 30 days" : "Rejected"}</Pill>} />} />}
          </>
        )}
      </PageState>
      {rejecting && <RejectModal c={rejecting} onClose={() => setRejecting(null)}
        onSubmit={(body) => { verdict(rejecting, body); setRejecting(null); }} />}
      {why && <WhyModal c={why} onClose={() => setWhy(null)} />}
    </>
  );
}

function CardList({ items, empty, render }: { items: Candidate[]; empty: string; render: (c: Candidate) => JSX.Element }) {
  return items.length ? <div className="flex flex-col gap-3">{items.map(render)}</div>
    : <p className="card px-6 py-8 text-sm text-muted">{empty}</p>;
}

export function RecCard({ c, onApprove, onReject, onSnooze, onWhy, done }: {
  c: Candidate; onApprove?: () => void; onReject?: () => void; onSnooze?: () => void; onWhy?: () => void; done?: JSX.Element;
}) {
  const r = c.resource;
  const likely = c.agent?.predicted_approval;
  return (
    <article className="card flex flex-wrap gap-5 p-5">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-[10px] bg-track text-ink"><TypeIcon type={r.type} /></span>
      <div className="flex min-w-[280px] flex-1 flex-col gap-2.5">
        <div>
          <p className="text-base font-semibold text-ink">{r.name}</p>
          <p className="text-[13px] text-muted">{[r.account, r.region, r.instance_type].filter(Boolean).join(" · ")}</p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Pill tone="approve" icon={<Zap size={12} />}>{describe(c)}</Pill>
          <TagPills tags={r.tags} />
          {r.iac_managed && <Pill tone="learned" icon={<GitBranch size={12} />}>Terraform-managed: you get a code diff</Pill>}
        </div>
        <div className="flex items-center gap-3">
          <Sparkline values={r.metrics?.daily_cpu_series} />
          <p className="text-[13px] text-ink">{c.signals_text}</p>
        </div>
        <p className="flex items-center gap-1.5 text-xs text-learned"><Icon name="sparkles" size={13} /> {memoryLine(c)}</p>
        {(c.warnings?.length ?? 0) > 0 && <p className="text-xs text-warn">{c.warnings!.join(" · ")}</p>}
      </div>
      <div className="flex flex-col items-end gap-2">
        <p className="flex items-baseline gap-0.5"><span className="text-2xl font-bold text-ink">{money(c.monthly_saving)}</span><span className="text-[13px] text-muted">/mo</span></p>
        <Pill tone={c.blast_radius.count ? "warn" : "plain"} icon={<Icon name="net" size={12} />}>Blast radius: {c.blast_radius.count}</Pill>
        {likely !== undefined && c.agent?.decision !== "suppress" && <p className="text-xs text-muted">Likely approval: {Math.round(likely * 100)}%</p>}
        <div className="mt-auto flex items-center gap-2 pt-1">
          {done ?? (
            <>
              <button className="btn btn-approve h-[29px]" onClick={onApprove}>Approve</button>
              <button className="btn btn-reject h-[29px]" onClick={onReject}>Reject</button>
              <button className="px-1 text-[13px] font-semibold text-muted hover:text-ink" onClick={onSnooze}>Snooze</button>
              <button className="px-1 text-[13px] font-semibold text-approve hover:underline" onClick={onWhy}>Why?</button>
            </>
          )}
        </div>
      </div>
    </article>
  );
}

function AskCard({ c, onApprove, onReject }: { c: Candidate; onApprove: () => void; onReject: () => void }) {
  return (
    <article className="card flex flex-wrap items-center gap-4 border-warn/40 p-5">
      <span className="flex size-10 items-center justify-center rounded-[10px] bg-warn-soft text-warn"><TypeIcon type={c.resource.type} /></span>
      <div className="flex min-w-[280px] flex-1 flex-col gap-1">
        <p className="text-sm font-semibold text-ink">{c.resource.name} · {describe(c)} · {money(c.monthly_saving)}/mo</p>
        <p className="text-sm italic text-ink">“{c.agent?.reason}”</p>
      </div>
      <button className="btn btn-approve h-[29px]" onClick={onApprove}>Approve</button>
      <button className="btn btn-reject h-[29px]" onClick={onReject}>Reject</button>
    </article>
  );
}

function SkipCard({ c, onOverride }: { c: Candidate; onOverride: () => void }) {
  const directive = c.agent?.reason?.startsWith("Directive:");
  const mems = c.agent?.memories ?? [];
  const cited = mems.find((m) => c.agent.cited_memory_ids?.includes(m.id)) ?? mems[0];
  const q = cited ? quoteParts(cited.text) : null;
  const why = directive ? `Hard rule: ${c.agent.reason.replace("Directive: ", "")}`
    : q?.reason ? `Matches learned rule “${q.reason}”${q.who ? ` · taught by ${q.who}${q.when ? `, ${q.when}` : ""}` : ""}`
      : c.agent?.reason;
  return (
    <article className="card flex flex-wrap items-center gap-4 px-5 py-3.5">
      <span className={directive ? "text-ink" : "text-learned"}>{directive ? <Lock size={15} /> : <Icon name="sparkles" size={15} />}</span>
      <div className="flex min-w-[280px] flex-1 flex-col gap-0.5">
        <p className="text-sm font-semibold text-ink">Skipped {c.resource.name}{c.resource.type === "s3" ? " (S3)" : ""}</p>
        <p className="text-[13px] text-muted">{why}</p>
      </div>
      <a href={directive ? "#settings/rules" : "#rules"} className="text-sm font-semibold text-approve hover:underline">{directive ? "View hard rules" : "View rule"}</a>
      <button className="text-[13px] font-medium text-muted hover:text-ink" onClick={onOverride}>Override</button>
    </article>
  );
}

function LearningBanner({ v }: { v: Verdict }) {
  if (v.learning_status === "learned" && v.learned_rule)
    return <Banner kind="mem" title={`Rule learned: ${v.learned_rule.text}`}>Confirmed {v.learned_rule.proof_count}× · look-alikes will be skipped on the next scan.</Banner>;
  if (v.learning_status === "learning") return <Banner kind="mem" title="Got it, learning…">“{v.reason}”</Banner>;
  if (v.learning_status === "timeout") return <Banner kind="mem" title="Saved; still consolidating">The rule will appear under Learned Rules shortly.</Banner>;
  if (v.learning_status === "error") return <Banner kind="warn" title="Saved, but memory is unavailable right now">Your reason is stored; learning retries on the next review.</Banner>;
  return <Banner kind="mem" title="Saved and learned">“{v.reason}”</Banner>;
}

/** Figma 14 reject modal. */
export function RejectModal({ c, onClose, onSubmit }: { c: Candidate; onClose: () => void; onSubmit: (b: Record<string, unknown>) => void }) {
  const [reason, setReason] = useState("");
  const [scope, setScope] = useState("similar");
  const [temporary, setTemporary] = useState(false);
  const [until, setUntil] = useState("");
  return (
    <Modal title={`Reject: ${c.resource.name}`} onClose={onClose}>
      <form className="flex flex-col gap-5" onSubmit={(e) => {
        e.preventDefault();
        if (reason.trim()) onSubmit({ decision: "reject", reason, scope, until_date: temporary && until ? `${until}T00:00:00Z` : null });
      }}>
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-ink">Why is this wrong? (required)</span>
          <textarea id="reason" className="field min-h-[84px]" required autoFocus value={reason}
            placeholder="e.g. It’s the DR standby for orders-db, idle on purpose." onChange={(e) => setReason(e.target.value)} />
          <span className="text-xs text-muted">This is what CloudSense learns from. One sentence is enough.</span>
        </label>
        <fieldset className="flex flex-col gap-3">
          <legend className="mb-2 text-sm font-medium text-ink">This applies to</legend>
          {[["similar", "All similar resources", "e.g. other standby replicas, in any account"], ["this_resource", "Only this resource", ""],
            ["team", "Everything my team owns", ""]].map(([v, l, hint]) => (
            <label key={v} className="flex cursor-pointer items-start gap-2.5">
              <input type="radio" name="scope" value={v} checked={scope === v} onChange={() => setScope(v)} className="mt-0.5 size-[18px] accent-approve" />
              <span className="flex flex-col"><span className="text-sm text-ink">{l}</span>{hint && <span className="text-xs text-muted">{hint}</span>}</span>
            </label>
          ))}
        </fieldset>
        <label className="flex cursor-pointer items-start gap-2.5">
          <input type="checkbox" checked={temporary} onChange={(e) => setTemporary(e.target.checked)} className="mt-0.5 size-4 accent-approve" />
          <span className="flex flex-col"><span className="text-sm text-ink">Temporary</span><span className="text-xs text-muted">Only until a date, e.g. after the Q4 migration</span></span>
        </label>
        {temporary && <input type="date" aria-label="Until" className="field w-48" value={until} onChange={(e) => setUntil(e.target.value)} />}
        <div className="-mx-5 flex justify-end gap-2 border-t border-rule px-5 pt-4">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-approve" disabled={!reason.trim()}>Reject</button>
        </div>
      </form>
    </Modal>
  );
}

function WhyModal({ c, onClose }: { c: Candidate; onClose: () => void }) {
  const ans = useLoad(() => post<{ text: string; based_on: MemoryHit[] }>(`/candidates/${c.id}/why`), [c.id]);
  return (
    <Modal title={`Why ${describe(c).toLowerCase()} ${c.resource.name}?`} onClose={onClose}>
      <p className="text-sm"><span className="font-medium">Agent:</span> {c.agent.reason}</p>
      <div className="mt-4">
        <PageState loading={ans.loading} error={ans.error} onRetry={ans.reload}>
          <p className="whitespace-pre-wrap text-sm">{ans.data?.text}</p>
          <h3 className="mb-2 mt-4 text-xs font-semibold tracking-[0.6px] text-muted">SOURCES</h3>
          <MemoryList hits={ans.data?.based_on ?? []} />
        </PageState>
      </div>
      <div className="mt-5 flex justify-end"><button className="btn" onClick={onClose}><X size={14} /> Close</button></div>
    </Modal>
  );
}
