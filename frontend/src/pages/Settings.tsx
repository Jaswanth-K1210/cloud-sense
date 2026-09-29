import { Check, Plus, Zap } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { api, ORG, patch, post, put, type Metrics, type OrgInfo, type Rule, type User } from "../api";
import { Banner, Checkbox, Chip, Field, Input, Select, Setting, Toggle } from "../components/form";
import { relTime, TopBar, useShell } from "../components/Shell";
import { PageState, useLoad } from "../components/ui";
import { AWS_REGIONS, mask, ROLES, SERVICES, SPEND, STARTER, TEAM_SIZES } from "./Onboarding";

const TABS = [["company", "Company"], ["accounts", "Accounts"], ["scanning", "Scanning"], ["slack", "Slack"],
  ["rules", "Rules"], ["safety", "Safety"], ["team", "Team"], ["memory", "Memory"]] as const;
type Tab = (typeof TABS)[number][0];

function useSaver() {
  const [state, setState] = useState<{ busy: boolean; msg: string | null; err: boolean }>({ busy: false, msg: null, err: false });
  const run = async (fn: () => Promise<unknown>, ok = "Saved.") => {
    setState({ busy: true, msg: null, err: false });
    try {
      await fn();
      setState({ busy: false, msg: ok, err: false });
    } catch (e) {
      setState({ busy: false, msg: (e as Error).message, err: true });
    }
  };
  const note = state.msg && <span role="status" className={`text-sm ${state.err ? "text-reject" : "text-success"}`}>{state.msg}</span>;
  return { busy: state.busy, run, note };
}

function Card({ title, desc, children, action }: { title: string; desc?: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="card flex flex-col gap-5 p-6">
      <div className="flex items-start gap-4">
        <div className="flex flex-1 flex-col gap-1">
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          {desc && <p className="text-[13px] text-muted">{desc}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export default function Settings({ tab: initial }: { tab?: string }) {
  const { me, refresh } = useShell();
  const tab: Tab = (TABS.find(([k]) => k === initial)?.[0] ?? "company") as Tab;
  const org = useLoad(() => api<OrgInfo>(`/orgs/${ORG}`));
  const admin = me.user.role === "admin";
  const reload = () => { org.reload(); refresh(); };

  return (
    <>
      <TopBar title="Settings" subtitle={`Workspace: ${org.data?.name ?? me.org.name}`} />
      <nav aria-label="Settings sections" className="flex gap-1 overflow-x-auto border-b border-rule">
        {TABS.map(([k, label]) => (
          <a key={k} href={`#settings/${k}`} aria-current={tab === k ? "page" : undefined}
            className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${tab === k ? "border-approve text-ink" : "border-transparent text-muted hover:text-ink"}`}>
            {label}
          </a>
        ))}
      </nav>
      {!admin && <Banner kind="info" title="Only admins can change workspace settings">You can view them; ask an admin to make changes.</Banner>}
      <PageState loading={org.loading && !org.data} error={org.error} onRetry={org.reload}>
        {org.data && (
          <fieldset disabled={!admin} className="flex flex-col gap-5">
            {tab === "company" && <Company org={org.data} onSaved={reload} />}
            {tab === "accounts" && <Accounts org={org.data} onSaved={reload} />}
            {tab === "scanning" && <Scanning org={org.data} />}
            {tab === "slack" && <Slack org={org.data} />}
            {tab === "rules" && <Rules org={org.data} />}
            {tab === "safety" && <Safety org={org.data} onSaved={reload} />}
            {tab === "team" && <Team selfId={me.user.id} />}
            {tab === "memory" && <Memory org={org.data} />}
          </fieldset>
        )}
      </PageState>
    </>
  );
}

function Company({ org, onSaved }: { org: OrgInfo; onSaved: () => void }) {
  const p = org.settings.profile ?? {};
  const [name, setName] = useState(org.name);
  const [role, setRole] = useState(p.role ?? "Platform");
  const [size, setSize] = useState(p.team_size ?? TEAM_SIZES[2]);
  const [spend, setSpend] = useState(p.spend ?? SPEND[2]);
  const { busy, run, note } = useSaver();
  return (
    <Card title="Company details" desc="Shown across CloudSense and used to name your private memory.">
      <Field label="Workspace (company) name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
      <div className="flex flex-col gap-2">
        <span className="text-[13px] font-medium text-ink">Your team’s role</span>
        <div className="flex flex-wrap gap-2">{ROLES.map((r) => <Chip key={r} selected={role === r} onClick={() => setRole(r)}>{r}</Chip>)}</div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Team size"><Select value={size} onChange={setSize} options={TEAM_SIZES} /></Field>
        <Field label="Monthly AWS spend (approx.)"><Select value={spend} onChange={setSpend} options={SPEND} /></Field>
      </div>
      <div className="flex items-center gap-3">
        <button className="btn btn-approve" disabled={busy || !name.trim()}
          onClick={() => run(async () => { await put(`/orgs/${ORG}/workspace`, { name, role, team_size: size, spend }); onSaved(); }, "Company details saved.")}>
          Save company details
        </button>
        {note}
      </div>
    </Card>
  );
}

function Accounts({ org, onSaved }: { org: OrgInfo; onSaved: () => void }) {
  const [adding, setAdding] = useState(false);
  const [alias, setAlias] = useState("");
  const [arn, setArn] = useState("");
  const add = useSaver();
  const [actionFor, setActionFor] = useState<string | null>(null);
  const [actionArn, setActionArn] = useState("");
  const act = useSaver();
  const scans = useLoad(() => api<{ started_at: string; status: string }[]>(`/orgs/${ORG}/scans`));
  const last = scans.data?.find((s) => s.status === "done");

  return (
    <Card title="Connected AWS accounts" desc="Read-only roles CloudSense assumes with your External ID. No keys are stored."
      action={<button className="btn btn-approve h-[29px]" onClick={() => setAdding(!adding)}><Plus size={14} /> Add account</button>}>
      {adding && (
        <div className="flex flex-col gap-3 rounded-xl border border-rule bg-paper p-4">
          <p className="text-sm text-ink">Create the role with External ID <code className="rounded bg-panel px-1">{org.external_id}</code> using <code>infra/cloudsense-readonly.yaml</code>, then paste its RoleArn.</p>
          <div className="grid gap-3 sm:grid-cols-[180px_1fr_auto] sm:items-end">
            <Field label="Alias"><Input value={alias} onChange={(e) => setAlias(e.target.value)} placeholder="acme-staging" /></Field>
            <Field label="Role ARN"><Input value={arn} onChange={(e) => setArn(e.target.value)} className="font-mono text-[13px]" placeholder="arn:aws:iam::…:role/CloudSenseReadOnlyRole" /></Field>
            <button className="btn btn-approve h-[39px]" disabled={add.busy || !alias.trim() || !arn.trim()}
              onClick={() => add.run(async () => {
                await post(`/orgs/${ORG}/accounts`, { alias, role_arn: arn.trim() });
                setAlias(""); setArn(""); setAdding(false); onSaved();
              }, "Account connected.")}>{add.busy ? "Verifying…" : "Verify connection"}</button>
          </div>
          {add.note}
        </div>
      )}
      <div className="overflow-x-auto rounded-xl border border-rule">
        <table className="w-full text-sm">
          <thead className="bg-paper text-left text-[11px] font-semibold tracking-[0.5px] text-muted">
            <tr><th className="px-4 py-2.5">ACCOUNT</th><th className="px-4">REGIONS</th><th className="px-4">LAST SCAN</th><th className="px-4">ACTIONS</th></tr>
          </thead>
          <tbody>
            {org.accounts.length === 0 && <tr><td colSpan={4} className="px-4 py-6 text-muted">No accounts yet. Add one to start scanning.</td></tr>}
            {org.accounts.map((a) => (
              <tr key={a.id} className="border-t border-rule">
                <td className="px-4 py-3"><p className="font-medium text-ink">{a.alias}</p><p className="text-xs text-muted">{mask(a.aws_account_id)} · read-only role</p></td>
                <td className="px-4"><div className="flex flex-wrap gap-1.5">{a.regions.map((g) => <span key={g} className="rounded-full bg-track px-2 py-0.5 text-xs text-ink">{g}</span>)}</div></td>
                <td className="px-4">
                  {last ? <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success"><Check size={12} /> Scanned {relTime(last.started_at)}</span>
                    : <span className="text-xs text-muted">Not scanned yet</span>}
                </td>
                <td className="px-4">
                  {a.action_role_arn ? <span className="inline-flex items-center gap-1 rounded-full bg-approve/10 px-2 py-0.5 text-xs font-medium text-approve"><Zap size={12} /> Actions enabled</span>
                    : actionFor === a.id ? (
                      <span className="flex items-center gap-2">
                        <Input aria-label="Action role ARN" value={actionArn} onChange={(e) => setActionArn(e.target.value)} placeholder="Action role ARN" className="h-8 w-64 font-mono text-xs" />
                        <button className="btn h-8" disabled={!actionArn.trim() || act.busy}
                          onClick={() => act.run(async () => { await patch(`/accounts/${a.id}`, { action_role_arn: actionArn.trim() }); setActionFor(null); onSaved(); })}>Save</button>
                      </span>
                    ) : <button className="btn h-[31px]" onClick={() => { setActionFor(a.id); setActionArn(""); }}>Enable actions</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {act.note}
    </Card>
  );
}

function Scanning({ org }: { org: OrgInfo }) {
  const [services, setServices] = useState<string[]>(org.settings.services ?? SERVICES.map(([k]) => k));
  const [schedule, setSchedule] = useState(org.settings.schedule ?? "manual");
  const [regions, setRegions] = useState<Record<string, string[]>>(Object.fromEntries(org.accounts.map((a) => [a.id, a.regions])));
  const { busy, run, note } = useSaver();
  return (
    <Card title="Scanning" desc="What CloudSense looks at, and how often.">
      <div className="flex flex-col gap-2">
        <span className="text-[13px] font-medium text-ink">Services</span>
        <div className="grid gap-3 sm:grid-cols-3">
          {SERVICES.map(([k, label]) => (
            <div key={k} className="flex items-center justify-between rounded-lg border border-rule px-3 py-2.5">
              <span className="text-sm text-ink">{label}</span>
              <Toggle label={label} checked={services.includes(k)} onChange={(on) => setServices((s) => (on ? [...s, k] : s.filter((x) => x !== k)))} />
            </div>
          ))}
        </div>
      </div>
      <div className="flex flex-col gap-2">
        <span className="text-[13px] font-medium text-ink">Schedule</span>
        <div className="inline-flex w-fit rounded-lg border border-rule bg-paper p-0.5">
          {(["daily", "weekly", "manual"] as const).map((s) => (
            <button key={s} type="button" aria-pressed={schedule === s} onClick={() => setSchedule(s)}
              className={`rounded-md px-4 py-1.5 text-[13px] font-medium capitalize ${schedule === s ? "bg-panel text-ink shadow-sm" : "text-muted"}`}>{s}</button>
          ))}
        </div>
      </div>
      {org.accounts.map((a) => (
        <div key={a.id} className="flex flex-col gap-2">
          <span className="text-[13px] font-medium text-ink">Regions for {a.alias}</span>
          <div className="flex flex-wrap gap-2">
            {AWS_REGIONS.map((g) => (
              <Chip key={g} selected={regions[a.id]?.includes(g)}
                onClick={() => setRegions((r) => ({ ...r, [a.id]: r[a.id].includes(g) ? r[a.id].filter((x) => x !== g) : [...r[a.id], g] }))}>{g}</Chip>
            ))}
          </div>
        </div>
      ))}
      <div className="flex items-center gap-3">
        <button className="btn btn-approve" disabled={busy || services.length === 0 || Object.values(regions).some((r) => r.length === 0)}
          onClick={() => run(async () => {
            await put(`/orgs/${ORG}/settings`, { services, schedule });
            await Promise.all(Object.entries(regions).map(([id, rs]) => patch(`/accounts/${id}`, { regions: rs })));
          })}>Save scanning settings</button>
        {note}
      </div>
    </Card>
  );
}

function Slack({ org }: { org: OrgInfo }) {
  const [status, setStatus] = useState<{ connected: boolean; team?: string; reason?: string; socket_mode?: boolean } | null>(null);
  const [channel, setChannel] = useState(org.settings.slack?.channel ?? "#cloudsense-review");
  const { busy, run, note } = useSaver();
  useEffect(() => { api<typeof status>("/slack/status").then(setStatus, () => undefined); }, []);
  return (
    <Card title="Slack" desc="Recommendations are posted to Slack for one-click reviews.">
      {status && (status.connected
        ? <Banner kind="ok" title={`Connected to ${status.team}`}>{status.socket_mode ? "Buttons in Slack work (Socket Mode)." : "Set SLACK_APP_TOKEN so button clicks reach CloudSense."}</Banner>
        : <Banner kind="warn" title="Slack isn’t connected">{status.reason} Reviews still work in the dashboard.</Banner>)}
      <Field label="Review channel" hint="Invite the bot to this channel."><Input value={channel} onChange={(e) => setChannel(e.target.value)} /></Field>
      <div className="flex items-center gap-3">
        <button className="btn btn-approve" disabled={busy} onClick={() => run(() => put(`/orgs/${ORG}/settings`, { slack: { ...org.settings.slack, channel } }))}>Save</button>
        {note}
      </div>
      <p className="text-[13px] text-muted">Map reviewers to Slack users in the <a href="#settings/team" className="font-medium text-approve">Team</a> tab.</p>
    </Card>
  );
}

function Rules({ org }: { org: OrgInfo }) {
  const [text, setText] = useState(org.hard_rules.join("\n"));
  const hard = useSaver();
  const [picked, setPicked] = useState<string[]>([]);
  const starter = useSaver();
  return (
    <>
      <Card title="Hard rules" desc="Written rules the agent never breaks, one per line. They always win over learned rules.">
        <textarea className="field min-h-28" value={text} onChange={(e) => setText(e.target.value)} placeholder="Never touch prod RDS" />
        <div className="flex items-center gap-3">
          <button className="btn btn-approve" disabled={hard.busy} onClick={() => hard.run(() => put(`/orgs/${ORG}/hard_rules`, { rules: text.split("\n") }), "Saved. The agent follows these on the next scan.")}>Save hard rules</button>
          {hard.note}
        </div>
      </Card>
      <Card title="Starter rules" desc="Common exceptions to add to memory. Already-added ones are harmless to add again.">
        <div className="grid gap-4 sm:grid-cols-2">
          {STARTER.map(([id, title, desc]) => (
            <Checkbox key={id} checked={picked.includes(id)} title={title} desc={desc}
              onChange={(v) => setPicked((p) => (v ? [...p, id] : p.filter((x) => x !== id)))} />
          ))}
        </div>
        <div className="flex items-center gap-3">
          <button className="btn" disabled={starter.busy || !picked.length}
            onClick={() => starter.run(async () => { await post(`/orgs/${ORG}/templates`, { rule_ids: picked }); setPicked([]); }, "Added to memory.")}>
            Add {picked.length || ""} to memory
          </button>
          {starter.note}
        </div>
      </Card>
    </>
  );
}

function Safety({ org, onSaved }: { org: OrgInfo; onSaved: () => void }) {
  const s = org.settings.safety ?? {};
  const [mode, setMode] = useState<"recommend" | "actions">(s.mode ?? "recommend");
  const [dryRun, setDryRun] = useState(s.dry_run ?? org.dry_run);
  const [confirm, setConfirm] = useState(s.type_confirm ?? true);
  const { busy, run, note } = useSaver();
  return (
    <Card title="Safety" desc="What CloudSense may do in your AWS accounts.">
      <Setting title="Mode" desc="Recommend only, or safe actions with backup and undo.">
        <select className="h-8 rounded-lg border border-rule bg-panel px-2 text-[13px]" value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}>
          <option value="recommend">Recommend only</option><option value="actions">Safe actions</option>
        </select>
      </Setting>
      <Setting title="Dry run" desc="Show planned AWS calls before anything runs."><Toggle label="Dry run" checked={dryRun} onChange={setDryRun} /></Setting>
      <Setting title="Type to confirm" desc="Reviewer types the resource name before an action runs."><Toggle label="Type to confirm" checked={confirm} onChange={setConfirm} /></Setting>
      {mode === "actions" && !org.accounts.some((a) => a.action_role_arn) && (
        <Banner kind="warn" title="No account has an action role yet">Enable actions on an account in the Accounts tab, or approved actions can’t run.</Banner>
      )}
      <div className="flex items-center gap-3">
        <button className="btn btn-approve" disabled={busy}
          onClick={() => run(async () => { await put(`/orgs/${ORG}/settings`, { safety: { mode, dry_run: dryRun, type_confirm: confirm } }); onSaved(); })}>Save safety settings</button>
        {note}
      </div>
    </Card>
  );
}

function Team({ selfId }: { selfId: string }) {
  const users = useLoad(() => api<User[]>(`/orgs/${ORG}/users`));
  const [rows, setRows] = useState<User[]>([]);
  useEffect(() => { if (users.data) setRows(users.data); }, [users.data]);
  const { busy, run, note } = useSaver();
  return (
    <Card title="Team" desc="Who can see, review and change things. Reviewers approve and reject; admins also manage settings.">
      <div className="overflow-x-auto rounded-xl border border-rule">
        <table className="w-full text-sm">
          <thead className="bg-paper text-left text-[11px] font-semibold tracking-[0.5px] text-muted">
            <tr><th className="px-4 py-2.5">MEMBER</th><th className="px-4">SLACK MEMBER ID</th><th className="px-4">ROLE</th></tr>
          </thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} className="border-t border-rule">
                <td className="px-4 py-3"><p className="font-medium text-ink">{u.name}{u.id === selfId ? " (you)" : ""}</p><p className="text-xs text-muted">{u.email}</p></td>
                <td className="px-4"><Input aria-label={`Slack member ID for ${u.name}`} className="h-8 w-44" value={u.slack_id ?? ""} placeholder="U0123ABCD"
                  onChange={(e) => setRows((rs) => rs.map((x) => (x.id === u.id ? { ...x, slack_id: e.target.value } : x)))} /></td>
                <td className="px-4">
                  <select aria-label={`Role for ${u.name}`} className="h-8 rounded-lg border border-rule bg-panel px-2 text-[13px] capitalize" value={u.role}
                    disabled={u.id === selfId} onChange={(e) => setRows((rs) => rs.map((x) => (x.id === u.id ? { ...x, role: e.target.value } : x)))}>
                    <option value="viewer">Viewer</option><option value="reviewer">Reviewer</option><option value="admin">Admin</option>
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-3">
        <button className="btn btn-approve" disabled={busy}
          onClick={() => run(() => Promise.all(rows.map((u) => patch(`/orgs/${ORG}/users/${u.id}`, { slack_id: u.slack_id ?? "", ...(u.id === selfId ? {} : { role: u.role }) }))))}>Save team</button>
        {note}
      </div>
      <p className="text-[13px] text-muted">Inviting teammates by email isn’t available yet; each person can create an account, and new accounts get their own workspace.</p>
    </Card>
  );
}

function Memory({ org }: { org: OrgInfo }) {
  const data = useLoad(async () => {
    const [m, rules] = await Promise.all([api<Metrics>(`/orgs/${ORG}/metrics`), api<Rule[]>(`/orgs/${ORG}/rules`)]);
    return { decisions: m.series.reduce((n, s) => n + s.approved + s.rejected, 0), rules: rules.length };
  });
  return (
    <Card title="Memory" desc={`Private to the ${org.name} workspace. Every rule links to the decisions that taught it.`}>
      <div className="flex gap-10">
        <div><p className="text-[26px] font-bold text-ink">{data.data?.decisions ?? "—"}</p><p className="text-xs text-muted">decisions stored</p></div>
        <div><p className="text-[26px] font-bold text-ink">{data.data?.rules ?? "—"}</p><p className="text-xs text-muted">rules learned</p></div>
      </div>
      <a href="#rules" className="btn w-fit">View learned rules</a>
    </Card>
  );
}
