import { Lock, X } from "lucide-react";
import { useState } from "react";
import { api, ORG, post, type OrgInfo, type Rule } from "../api";
import { Icon } from "../components/Icon";
import { Banner, Chip } from "../components/form";
import { FilterSelect, Pill, quoteParts } from "../components/bits";
import { relTime, TopBar, useShell } from "../components/Shell";
import { PageState, useLoad } from "../components/ui";

type LRule = Rule & { starter?: boolean; protected?: string[]; last_used?: string | null };

function scopeOf(r: LRule): string {
  const acct = r.tags.find((t) => t.startsWith("account:"))?.slice(8);
  const team = r.tags.find((t) => t.startsWith("team:"))?.slice(5);
  return team && team !== "None" ? `${team} team` : acct ? acct : "All accounts";
}
function teacher(r: LRule): string {
  const q = r.sources.map((s) => quoteParts(s.text)).find((x) => x.who);
  return q?.who ?? (r.starter ? "Starter rule" : "—");
}
function usage(r: LRule): string {
  const n = r.protected?.length ?? 0;
  if (!n) return "Not used yet";
  return `Skipped ${n} resource${n === 1 ? "" : "s"}${r.last_used ? ` · ${relTime(r.last_used)}` : ""}`;
}

/** Figma 17: learned rules with evidence. */
export default function Rules() {
  const { me, refresh } = useShell();
  const rules = useLoad(() => api<LRule[]>(`/orgs/${ORG}/rules`));
  const org = useLoad(() => api<OrgInfo>(`/orgs/${ORG}`));
  const [kind, setKind] = useState<"all" | "learned" | "starter" | "hard">("all");
  const [team, setTeam] = useState("all");
  const [account, setAccount] = useState("all");
  const [open, setOpen] = useState<LRule | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const admin = me.user.role === "admin";

  const all = rules.data ?? [];
  const hard = org.data?.hard_rules ?? [];
  const learned = all.filter((r) => !r.starter), starter = all.filter((r) => r.starter);
  const teams = [...new Set(all.map((r) => r.tags.find((t) => t.startsWith("team:"))?.slice(5)).filter((t) => t && t !== "None") as string[])];
  const accounts = [...new Set(all.map((r) => r.tags.find((t) => t.startsWith("account:"))?.slice(8)).filter(Boolean) as string[])];
  const shown = (kind === "learned" ? learned : kind === "starter" ? starter : kind === "hard" ? [] : all)
    .filter((r) => team === "all" || r.tags.includes(`team:${team}`))
    .filter((r) => account === "all" || r.tags.includes(`account:${account}`));
  const reviews = all.reduce((n, r) => n + r.sources.length, 0);

  const remove = async (r: LRule) => {
    try {
      await api(`/orgs/${ORG}/rules/${r.id}`, { method: "DELETE" });
      setOpen(null); setConfirming(false);
      setMsg({ ok: true, text: "Rule deleted. CloudSense may recommend those resources again." });
      rules.reload(); refresh();
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  };
  const report = async (r: LRule) => {
    try {
      await post(`/orgs/${ORG}/rules/${r.id}/report`, { reason: "Reported as wrong from Learned Rules" });
      setMsg({ ok: true, text: "Reported. Admins can see it in Activity and delete the rule if it’s wrong." });
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  };

  return (
    <>
      <TopBar title="Learned Rules" subtitle={`${all.length} rule${all.length === 1 ? "" : "s"} learned from ${reviews} review${reviews === 1 ? "" : "s"}`} />
      {msg && <Banner kind={msg.ok ? "ok" : "err"} title={msg.text} />}
      <div className="flex flex-wrap items-center gap-2.5">
        <Chip selected={kind === "all"} onClick={() => setKind("all")}>All ({all.length + hard.length})</Chip>
        <Chip selected={kind === "learned"} onClick={() => setKind("learned")}>Learned ({learned.length})</Chip>
        <Chip selected={kind === "starter"} onClick={() => setKind("starter")}>Starter ({starter.length})</Chip>
        <Chip selected={kind === "hard"} onClick={() => setKind("hard")}>Hard rules ({hard.length})</Chip>
        <span className="flex-1" />
        <FilterSelect label="Team" value={team} onChange={setTeam} options={[["all", "Team: All"], ...teams.map((t) => [t, `Team: ${t}`] as [string, string])]} />
        <FilterSelect label="Account" value={account} onChange={setAccount} options={[["all", "Account: All"], ...accounts.map((a) => [a, `Account: ${a}`] as [string, string])]} />
      </div>
      <PageState loading={rules.loading && !rules.data} error={rules.error} onRetry={rules.reload}>
        <div className="flex flex-wrap items-start gap-5">
          <div className="flex min-w-[340px] flex-1 flex-col gap-5">
            {(kind === "all" || kind === "hard") && (
              <section className="card">
                <div className="flex items-center gap-2 px-5 py-3.5">
                  <Lock size={14} className="text-ink" /><h2 className="flex-1 text-sm font-semibold text-ink">Hard rules</h2>
                  <Pill>Always enforced</Pill>
                </div>
                {hard.length === 0 && <p className="border-t border-rule px-5 py-3 text-sm text-muted">No hard rules. Add them in <a href="#settings/rules" className="text-approve">Settings → Rules</a>.</p>}
                {hard.map((h) => <p key={h} className="flex items-center gap-2 border-t border-rule px-5 py-3 text-sm text-ink"><Lock size={14} className="text-muted" /> {h}</p>)}
              </section>
            )}
            {kind !== "hard" && (
              <section className="card overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-[11px] font-semibold tracking-[0.5px] text-muted">
                    <tr><th className="px-5 py-3">RULE</th><th className="px-3">CONFIRMED</th><th className="px-3">TAUGHT BY</th><th className="px-3">SCOPE</th></tr>
                  </thead>
                  <tbody>
                    {shown.length === 0 && <tr><td colSpan={4} className="border-t border-rule px-5 py-8 text-muted">No rules yet. Reject a recommendation with a reason and CloudSense learns from it.</td></tr>}
                    {shown.map((r) => (
                      <tr key={r.id} onClick={() => { setOpen(r); setConfirming(false); }}
                        className={`cursor-pointer border-t border-rule hover:bg-paper ${open?.id === r.id ? "bg-paper" : ""}`}>
                        <td className="px-5 py-3.5"><p className="font-medium text-ink">{r.text}</p><p className="text-xs text-muted">{usage(r)}</p></td>
                        <td className="px-3">{r.starter ? <Pill>Starter</Pill> : <Pill tone="learned">{r.proof_count}×</Pill>}</td>
                        <td className="px-3 text-ink">{teacher(r)}</td>
                        <td className="px-3 text-ink">{scopeOf(r)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}
          </div>
          <aside className="card flex w-full flex-col gap-5 p-5 lg:w-[380px]">
            {!open ? <p className="text-sm text-muted">Select a rule to see the rejections that taught it and what it protected.</p> : (
              <>
                <div className="flex items-center gap-2">
                  <Icon name="sparkles" size={14} className="text-learned" />
                  <p className="flex-1 text-[11px] font-semibold tracking-[0.8px] text-learned">{open.starter ? "STARTER RULE" : "LEARNED RULE"}</p>
                  <button aria-label="Close" onClick={() => setOpen(null)} className="text-muted hover:text-ink"><X size={16} /></button>
                </div>
                <h2 className="text-xl font-bold tracking-[-0.2px] text-ink">{open.text}</h2>
                <div className="flex flex-wrap gap-2"><Pill tone="learned">Confirmed {open.proof_count}×</Pill><Pill>{scopeOf(open)}</Pill></div>
                <div className="flex flex-col gap-3">
                  <p className="text-[13px] font-semibold text-ink">Evidence</p>
                  {open.sources.length === 0 && <p className="text-sm text-muted">No source decisions recorded.</p>}
                  {open.sources.map((s) => {
                    const q = quoteParts(s.text);
                    return (
                      <div key={s.id} className="border-l-2 border-learned-line pl-3">
                        <p className="text-sm italic text-ink">“{q.reason ?? s.text.slice(0, 200)}”</p>
                        {(q.who || q.when) && <p className="mt-1 text-xs text-muted">{[q.who, q.when].filter(Boolean).join(" · ")}</p>}
                      </div>
                    );
                  })}
                </div>
                <div className="flex flex-col gap-2">
                  <p className="text-[13px] font-semibold text-ink">History</p>
                  <ol className="flex flex-col gap-2">
                    {open.sources.map((s, i) => {
                      const q = quoteParts(s.text);
                      return (
                        <li key={s.id} className="flex items-baseline gap-2 text-[13px]">
                          <span className="size-2 shrink-0 rounded-full bg-learned" />
                          <span className="w-12 shrink-0 text-muted">{q.when ?? "—"}</span>
                          <span className="text-ink">{i === 0
                            ? (q.who ? `Created from ${q.who}’s rejection` : open.starter ? "Accepted as a starter rule" : "Created from a past decision")
                            : `Confirmed by ${q.who ?? "a reviewer"} (${i + 1}×)`}</span>
                        </li>
                      );
                    })}
                  </ol>
                </div>
                <div className="flex flex-col gap-2">
                  <p className="text-[13px] font-semibold text-ink">Protected resources</p>
                  <div className="flex flex-wrap gap-1.5">
                    {(open.protected ?? []).length ? open.protected!.map((n) => <Pill key={n}>{n}</Pill>) : <p className="text-sm text-muted">None yet.</p>}
                  </div>
                </div>
                {confirming ? (
                  <div className="flex flex-col gap-2 rounded-lg bg-reject/5 p-3">
                    <p className="text-sm text-ink">Delete this rule? CloudSense may recommend these resources again.</p>
                    <div className="flex gap-2"><button className="btn btn-reject" onClick={() => remove(open)}>Delete rule</button><button className="btn" onClick={() => setConfirming(false)}>Keep it</button></div>
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {admin && <button className="btn btn-reject h-[29px]" onClick={() => setConfirming(true)}>Delete rule</button>}
                    <button className="btn h-[31px]" onClick={() => report(open)}>Report as wrong</button>
                  </div>
                )}
                <p className="text-xs text-muted">Admins only can delete. After deleting, CloudSense may recommend these resources again.</p>
              </>
            )}
          </aside>
        </div>
      </PageState>
    </>
  );
}
