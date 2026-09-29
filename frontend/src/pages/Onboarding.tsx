import { Check, Copy, ExternalLink, Hash, Lock, Plus, X, Zap } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { api, ORG, patch, post, put, type Me, type OrgInfo, type User } from "../api";
import { Icon } from "../components/Icon";
import { Banner, Checkbox, Chip, Field, Input, Logo, Select, Setting, Toggle } from "../components/form";

const STEPS = ["Workspace", "Connect AWS", "Accounts & regions", "Slack", "Known rules", "Safety"];
export const ROLES = ["Platform", "DevOps", "FinOps", "Engineering lead", "Other"];
export const TEAM_SIZES = ["1–5 engineers", "6–20 engineers", "21–50 engineers", "51–200 engineers", "200+ engineers"];
export const SPEND = ["Under $5k", "$5k – $20k", "$20k – $50k", "$50k – $200k", "$200k+"];
export const SERVICES: [string, string][] = [["ec2", "EC2"], ["ebs", "EBS volumes"], ["snapshot", "Snapshots"],
  ["eip", "Elastic IPs"], ["rds", "RDS"], ["s3", "S3"]];
export const AWS_REGIONS = ["us-east-1", "us-east-2", "us-west-1", "us-west-2", "ca-central-1", "eu-west-1", "eu-west-2",
  "eu-central-1", "eu-north-1", "ap-south-1", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1", "sa-east-1"];
const HARD_RULES = ["Never touch resources tagged do_not_terminate=true", "Never change production databases",
  "Never change anything tagged compliance:* without a second review"];
export const STARTER: [string, string, string, boolean][] = [
  ["dr-standby", "DR / standby replicas", "Idle by design", true],
  ["month-end-batch", "Month-end batch jobs", "Spiky, low average CPU", true],
  ["legal-archive", "Audit & legal archives", "Retention required", true],
  ["blue-green", "Blue/green standbys", "Rollback path", true],
  ["license-pinned", "License-pinned servers", "Instance type is locked", true],
  ["on-call-debug", "On-call debug hosts", "Used during incidents", true],
  ["ci-runners", "CI runners", "Recycled weekly", true],
  ["bastion", "Bastion hosts", "Low traffic, but critical", true],
  ["nat-instance", "NAT instances", "On the network path", false],
  ["log-shipper", "Log shippers", "Low CPU, always on", false],
];
const READONLY_PERMISSIONS = ["ec2:Describe* (instances, volumes, snapshots, images, addresses, security groups)",
  "autoscaling:DescribeAutoScalingGroups", "elasticloadbalancing:Describe*", "rds:Describe*, rds:ListTagsForResource",
  "s3:ListAllMyBuckets, s3:GetBucketLocation, s3:GetBucketTagging, s3:GetLifecycleConfiguration",
  "cloudwatch:GetMetricData, cloudwatch:ListMetrics", "tag:GetResources",
  "Optional: ce:GetCostAndUsage, cost-optimization-hub:ListRecommendations"];
const TEMPLATE_URL = import.meta.env.VITE_READONLY_TEMPLATE_URL as string | undefined;
const ACTION_TEMPLATE_URL = import.meta.env.VITE_ACTION_TEMPLATE_URL as string | undefined;

function launchUrl(template: string | undefined, stack: string, org: OrgInfo): string | null {
  if (!template) return null;
  const p = new URLSearchParams({ templateURL: template, stackName: stack, param_ExternalId: org.external_id,
    param_CloudSensePrincipalArn: org.principal_arn });
  return `https://console.aws.amazon.com/cloudformation/home#/stacks/create/review?${p}`;
}

export const mask = (id: string) => (id && id.length >= 8 ? `${id.slice(0, 4)}…${id.slice(-4)}` : id || "unknown");

export default function Onboarding({ me, onDone }: { me: Me; onDone: (scanId: string | null) => void }) {
  const [step, setStep] = useState(Math.min(Math.max(me.org.settings.onboarding_step ?? 1, 1), 6));
  const [org, setOrg] = useState<OrgInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api<OrgInfo>(`/orgs/${ORG}`).then(setOrg, (e) => setError(e.message)); }, [step]);
  const go = async (n: number) => {
    await put(`/orgs/${ORG}/settings`, { onboarding_step: n }).catch(() => undefined);
    setStep(n);
    window.scrollTo(0, 0);
  };

  return (
    <div className="min-h-screen bg-paper">
      <header className="sticky top-0 z-10 bg-panel">
        <div className="flex h-16 items-center px-8">
          <Logo />
          <span className="flex-1" />
          <span className="text-[13px] text-muted">Step {step} of 6</span>
        </div>
        <div className="h-1 bg-track"><div className="h-full bg-approve transition-all" style={{ width: `${(step / 6) * 100}%` }} /></div>
      </header>
      <div className="mx-auto flex max-w-[1200px] gap-12 px-8 py-10">
        <nav aria-label="Setup steps" className="hidden w-60 shrink-0 md:block">
          <p className="mb-4 text-[11px] font-semibold tracking-[0.6px] text-muted">SET UP CLOUDSENSE</p>
          <ol className="flex flex-col gap-3">
            {STEPS.map((label, i) => {
              const n = i + 1, done = n < step, current = n === step;
              return (
                <li key={label} className="flex items-center gap-3" aria-current={current ? "step" : undefined}>
                  <span className={`flex size-6 items-center justify-center rounded-full text-xs font-semibold ${done ? "bg-approve text-white" : current ? "bg-ink text-white" : "border border-rule bg-panel text-muted"}`}>
                    {done ? <Check size={12} strokeWidth={3} /> : n}
                  </span>
                  <span className={`text-sm ${current ? "font-semibold text-ink" : done ? "text-ink" : "text-muted"}`}>{label}</span>
                </li>
              );
            })}
          </ol>
        </nav>
        <main className="card min-w-0 flex-1 p-8">
          {error && <Banner kind="err" title={error} />}
          {!org ? <p className="text-muted" role="status">Loading…</p> : (
            <>
              {step === 1 && <StepWorkspace org={org} next={() => go(2)} />}
              {step === 2 && <StepAws org={org} setOrg={setOrg} back={() => go(1)} next={() => go(3)} />}
              {step === 3 && <StepScope org={org} back={() => go(2)} next={() => go(4)} />}
              {step === 4 && <StepSlack org={org} back={() => go(3)} next={() => go(5)} />}
              {step === 5 && <StepRules back={() => go(4)} next={() => go(6)} />}
              {step === 6 && <StepSafety org={org} back={() => go(5)} done={onDone} />}
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function StepHead({ title, desc }: { title: string; desc: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-2">
      <h1 className="text-[26px] font-bold tracking-[-0.4px] text-ink">{title}</h1>
      <p className="text-[15px] leading-normal text-muted">{desc}</p>
    </div>
  );
}

function Footer({ back, next, nextLabel = "Continue", busy, disabled, skip, error }: {
  back?: () => void; next: () => void; nextLabel?: string; busy?: boolean; disabled?: boolean; skip?: () => void;
  error?: string | null;
}) {
  return (
    <div className="mt-8 flex flex-col gap-3 border-t border-rule pt-5">
      {error && <Banner kind="err" title={error} />}
      <div className="flex items-center gap-3">
        {back && <button type="button" className="btn" onClick={back}>Back</button>}
        <span className="flex-1" />
        {skip && <button type="button" className="btn-ghost" onClick={skip}>Skip for now</button>}
        <button type="button" className="btn btn-approve h-[35px] px-4" onClick={next} disabled={busy || disabled}>
          {busy ? "Saving…" : nextLabel}
        </button>
      </div>
    </div>
  );
}

// ---------- step 1 ----------
function StepWorkspace({ org, next }: { org: OrgInfo; next: () => void }) {
  const p = org.settings.profile ?? {};
  const [name, setName] = useState(org.name);
  const [role, setRole] = useState(p.role ?? "Platform");
  const [size, setSize] = useState(p.team_size ?? TEAM_SIZES[2]);
  const [spend, setSpend] = useState(p.spend ?? SPEND[2]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await put(`/orgs/${ORG}/workspace`, { name, role, team_size: size, spend });
      next();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <StepHead title="Create your workspace" desc="This is where your team’s AWS accounts, reviews and learned rules live." />
      <div className="flex flex-col gap-5">
        <Field label="Workspace name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme" /></Field>
        <div className="flex flex-col gap-2">
          <span className="text-[13px] font-medium text-ink">Your role</span>
          <div className="flex flex-wrap gap-2">
            {ROLES.map((r) => <Chip key={r} selected={role === r} onClick={() => setRole(r)}>{r}</Chip>)}
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Team size"><Select value={size} onChange={setSize} options={TEAM_SIZES} /></Field>
          <Field label="Monthly AWS spend (approx.)"><Select value={spend} onChange={setSpend} options={SPEND} /></Field>
        </div>
        <Banner kind="mem" title={`A private memory is created for ${name || "your workspace"}`}>
          Everything CloudSense learns from your team stays in this workspace. It is never shared with other customers.
        </Banner>
      </div>
      <Footer next={save} busy={busy} disabled={!name.trim()} error={error} />
    </>
  );
}

// ---------- step 2 ----------
function StepAws({ org, setOrg, back, next }: {
  org: OrgInfo; setOrg: (o: OrgInfo) => void; back: () => void; next: () => void;
}) {
  const [arn, setArn] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState<{ alias: string; aws_account_id: string; resource_count: number; regions: string[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showPerms, setShowPerms] = useState(false);
  const url = launchUrl(TEMPLATE_URL, "cloudsense-readonly", org);

  const verify = async () => {
    setBusy(true);
    setError(null);
    setOk(null);
    try {
      const slug = org.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "aws";
      const alias = org.accounts.length ? `${slug}-${org.accounts.length + 1}` : `${slug}-prod`;
      const r = await post<{ alias: string; aws_account_id: string; resource_count: number; regions: string[] }>(
        `/orgs/${ORG}/accounts`, { alias, role_arn: arn.trim() });
      setOk(r);
      setArn("");
      setOrg(await api<OrgInfo>(`/orgs/${ORG}`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const [errTitle, errFix] = (error ?? "").split(" Fix: ");

  return (
    <>
      <StepHead title="Connect your AWS account"
        desc="CloudSense needs read-only access. You create a role in your own AWS account; we never see your passwords or keys." />
      <div className="flex flex-col gap-5">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-end gap-2">
            <div className="flex-1"><Field label="Your External ID"><Input readOnly value={org.external_id} className="font-mono text-[13px]" /></Field></div>
            <button type="button" className="btn h-[39px]" onClick={() => {
              navigator.clipboard?.writeText(org.external_id).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); });
            }}><Copy size={14} /> {copied ? "Copied" : "Copy"}</button>
          </div>
          <p className="text-xs text-muted">Unique to your workspace. It stops anyone else from using your role.</p>
        </div>

        <section className="rounded-xl border border-rule p-5">
          <div className="flex flex-wrap items-start gap-4">
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <p className="text-[15px] font-semibold text-ink">Create the read-only role</p>
              <p className="text-[13px] text-muted">Opens AWS CloudFormation with the template and your External ID prefilled.</p>
            </div>
            {url ? (
              <a href={url} target="_blank" rel="noreferrer" className="btn border-ink bg-ink text-white hover:opacity-90">
                Launch Stack in AWS <ExternalLink size={14} />
              </a>
            ) : (
              <span className="text-xs text-muted">Set VITE_READONLY_TEMPLATE_URL to enable one-click launch.<br />
                Or deploy <code>infra/cloudsense-readonly.yaml</code> manually.</span>
            )}
          </div>
          <ol className="mt-4 flex flex-col gap-2.5">
            {["Click Launch Stack and sign in to AWS.", "Tick “I acknowledge…” and click Create stack.",
              "Copy RoleArn from the Outputs tab (takes about a minute)."].map((t, i) => (
              <li key={t} className="flex items-center gap-2.5 text-sm text-ink">
                <span className="flex size-5 items-center justify-center rounded-full bg-track text-[11px] font-semibold text-muted">{i + 1}</span>{t}
              </li>
            ))}
          </ol>
        </section>

        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Field label="Role ARN">
              <Input value={arn} onChange={(e) => setArn(e.target.value)} className="font-mono text-[13px]"
                placeholder="arn:aws:iam::123456789012:role/CloudSenseReadOnlyRole"
                onKeyDown={(e) => e.key === "Enter" && arn.trim() && verify()} />
            </Field>
          </div>
          <button type="button" className="btn btn-approve h-[39px]" onClick={verify} disabled={busy || !arn.trim()}>
            {busy ? "Verifying…" : "Verify connection"}
          </button>
        </div>

        {ok && (
          <Banner kind="ok" title={`Connected: account ${mask(ok.aws_account_id)} (${ok.alias}) · read-only`}>
            {ok.resource_count ? `Found ${ok.resource_count} resources in ${ok.regions.join(" and ")}.` : `Scanning ${ok.regions.join(", ")}.`}
          </Banner>
        )}
        {error && <Banner kind="err" title={errTitle}>{errFix ? `Fix: ${errFix}` : null}</Banner>}

        {org.accounts.length > 0 && !ok && (
          <ul className="flex flex-col gap-1.5">
            {org.accounts.map((a) => (
              <li key={a.id} className="flex items-center gap-2 text-sm text-ink">
                <Check size={14} className="text-success" /> {a.alias} <span className="text-muted">· {mask(a.aws_account_id)} · read-only</span>
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-wrap gap-6">
          <button type="button" className="flex items-center gap-1.5 text-sm font-medium text-approve" onClick={() => setShowPerms(!showPerms)}>
            <Icon name="eye" size={14} /> {showPerms ? "Hide" : "View"} the exact permissions
          </button>
          {ok && (
            <button type="button" className="flex items-center gap-1.5 text-sm font-medium text-approve" onClick={() => setOk(null)}>
              <Plus size={14} /> Add another account
            </button>
          )}
        </div>
        {showPerms && (
          <ul className="list-disc rounded-lg bg-paper py-3 pl-8 pr-4 font-mono text-xs leading-6 text-ink">
            {READONLY_PERMISSIONS.map((p) => <li key={p}>{p}</li>)}
          </ul>
        )}
        <p className="text-xs text-muted">Developers: enter <code>local</code> to use this server’s own AWS credentials.</p>
      </div>
      <Footer back={back} next={next} disabled={org.accounts.length === 0} />
    </>
  );
}

// ---------- step 3 ----------
function StepScope({ org, back, next }: { org: OrgInfo; back: () => void; next: () => void }) {
  const [rows, setRows] = useState(org.accounts.map((a) => ({ ...a })));
  const [services, setServices] = useState<string[]>(org.settings.services ?? SERVICES.map(([k]) => k));
  const [schedule, setSchedule] = useState(org.settings.schedule ?? "daily");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const update = (id: string, change: Partial<(typeof rows)[number]>) =>
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...change } : r)));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await Promise.all(rows.map((r) => patch(`/accounts/${r.id}`, { alias: r.alias, regions: r.regions })));
      await put(`/orgs/${ORG}/settings`, { services, schedule });
      next();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <StepHead title="Choose what to scan" desc="Pick accounts, regions and services. We preselected the regions where we found resources." />
      <div className="flex flex-col gap-6">
        <div className="overflow-x-auto rounded-xl border border-rule">
          <table className="w-full text-sm">
            <thead className="bg-paper text-left text-[11px] font-semibold tracking-[0.5px] text-muted">
              <tr><th className="px-4 py-2.5">ACCOUNT</th><th className="px-4">ALIAS</th><th className="px-4">REGIONS</th><th className="px-4">STATUS</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-rule align-middle">
                  <td className="px-4 py-3"><p className="font-medium text-ink">{r.alias}</p><p className="text-xs text-muted">{mask(r.aws_account_id)}</p></td>
                  <td className="px-4"><Input aria-label={`Alias for ${r.alias}`} value={r.alias} className="h-8 w-32"
                    onChange={(e) => update(r.id, { alias: e.target.value })} /></td>
                  <td className="px-4">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {r.regions.map((g) => (
                        <span key={g} className="flex items-center gap-1 rounded-full bg-track px-2 py-0.5 text-xs text-ink">
                          {g}
                          {r.regions.length > 1 && (
                            <button type="button" aria-label={`Remove ${g}`} onClick={() => update(r.id, { regions: r.regions.filter((x) => x !== g) })}>
                              <X size={11} />
                            </button>
                          )}
                        </span>
                      ))}
                      <select aria-label="Add region" value="" className="rounded-full border border-dashed border-rule bg-panel px-2 py-0.5 text-xs text-muted"
                        onChange={(e) => e.target.value && update(r.id, { regions: [...r.regions, e.target.value] })}>
                        <option value="">+ Add</option>
                        {AWS_REGIONS.filter((g) => !r.regions.includes(g)).map((g) => <option key={g}>{g}</option>)}
                      </select>
                    </div>
                  </td>
                  <td className="px-4"><span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success"><Check size={12} /> Connected</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex flex-col gap-2">
          <span className="text-[13px] font-medium text-ink">Services</span>
          <div className="grid gap-3 sm:grid-cols-3">
            {SERVICES.map(([k, label]) => (
              <div key={k} className="flex items-center justify-between rounded-lg border border-rule px-3 py-2.5">
                <span className="text-sm text-ink">{label}</span>
                <Toggle label={label} checked={services.includes(k)}
                  onChange={(on) => setServices((s) => (on ? [...s, k] : s.filter((x) => x !== k)))} />
              </div>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <span className="text-[13px] font-medium text-ink">Scan schedule</span>
          <div className="inline-flex w-fit rounded-lg border border-rule bg-paper p-0.5">
            {(["daily", "weekly", "manual"] as const).map((s) => (
              <button key={s} type="button" aria-pressed={schedule === s} onClick={() => setSchedule(s)}
                className={`rounded-md px-4 py-1.5 text-[13px] font-medium capitalize ${schedule === s ? "bg-panel text-ink shadow-sm" : "text-muted"}`}>{s}</button>
            ))}
          </div>
        </div>
        <Banner kind="info" icon={<Zap size={18} className="text-approve" />} title="Your first scan takes about 60 seconds">
          We read 14 days of CloudWatch metrics. Nothing in your account is changed.
        </Banner>
      </div>
      <Footer back={back} next={save} busy={busy} disabled={services.length === 0} error={error} />
    </>
  );
}

// ---------- step 4 ----------
interface SlackStatus { connected: boolean; team?: string; url?: string; reason?: string; socket_mode?: boolean }

function StepSlack({ org, back, next }: { org: OrgInfo; back: () => void; next: () => void }) {
  const [status, setStatus] = useState<SlackStatus | null>(null);
  const [channel, setChannel] = useState(org.settings.slack?.channel ?? "#cloudsense-review");
  const [users, setUsers] = useState<User[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<SlackStatus>("/slack/status").then(setStatus, () => setStatus({ connected: false, reason: "Couldn't check." }));
    api<User[]>(`/orgs/${ORG}/users`).then(setUsers, () => undefined);
  }, []);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await put(`/orgs/${ORG}/settings`, { slack: { channel } });
      await Promise.all(users.map((u) => patch(`/orgs/${ORG}/users/${u.id}`, { slack_id: u.slack_id ?? "" })));
      next();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <StepHead title="Connect Slack" desc="Engineers review recommendations where they already work. Rejecting takes one sentence." />
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-4 rounded-xl border border-rule p-5">
          <span className="flex size-10 items-center justify-center rounded-lg bg-track text-ink"><Hash size={20} /></span>
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <p className="text-[15px] font-semibold text-ink">Slack workspace</p>
            <p className="text-[13px] text-muted">
              {!status ? "Checking…" : status.connected ? `Connected to ${status.team}${status.socket_mode ? "" : " (set SLACK_APP_TOKEN to receive button clicks)"}` : `Not connected. ${status.reason}`}
            </p>
          </div>
          {status && !status.connected && (
            <a href="https://api.slack.com/apps" target="_blank" rel="noreferrer" className="btn border-[#4a154b] bg-[#4a154b] text-white hover:opacity-90">
              Create Slack app <ExternalLink size={14} />
            </a>
          )}
        </div>
        <Field label="Review channel" hint="New recommendations are posted here, batched per scan.">
          <Input value={channel} onChange={(e) => setChannel(e.target.value)} />
        </Field>
        <div className="flex flex-col gap-2">
          <span className="text-[13px] font-medium text-ink">Map reviewers</span>
          <div className="overflow-x-auto rounded-xl border border-rule">
            <table className="w-full text-sm">
              <thead className="bg-paper text-left text-[11px] font-semibold tracking-[0.5px] text-muted">
                <tr><th className="px-4 py-2.5">MEMBER</th><th className="px-4">SLACK MEMBER ID</th><th className="px-4">ROLE</th></tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-t border-rule">
                    <td className="px-4 py-3"><p className="font-medium text-ink">{u.name}</p><p className="text-xs text-muted">{u.email}</p></td>
                    <td className="px-4"><Input aria-label={`Slack member ID for ${u.name}`} value={u.slack_id ?? ""} placeholder="U0123ABCD" className="h-8 w-44"
                      onChange={(e) => setUsers((us) => us.map((x) => (x.id === u.id ? { ...x, slack_id: e.target.value } : x)))} /></td>
                    <td className="px-4 capitalize text-ink">{u.role}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted">Find a member ID in Slack: open the person’s profile → ⋮ → Copy member ID.</p>
        </div>
      </div>
      <Footer back={back} next={save} busy={busy} skip={next} error={error} />
    </>
  );
}

// ---------- step 5 ----------
function StepRules({ back, next }: { back: () => void; next: () => void }) {
  const [hard, setHard] = useState<Record<string, boolean>>({ [HARD_RULES[0]]: true, [HARD_RULES[1]]: true, [HARD_RULES[2]]: false });
  const [custom, setCustom] = useState("");
  const [starter, setStarter] = useState<Record<string, boolean>>(Object.fromEntries(STARTER.map(([id, , , on]) => [id, on])));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const addCustom = () => {
    if (custom.trim()) setHard((h) => ({ ...h, [custom.trim()]: true }));
    setCustom("");
  };
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await put(`/orgs/${ORG}/hard_rules`, { rules: Object.keys(hard).filter((r) => hard[r]) });
      const ids = Object.keys(starter).filter((k) => starter[k]);
      if (ids.length) await post(`/orgs/${ORG}/templates`, { rule_ids: ids });
      next();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <StepHead title="Rules you already know"
        desc="Hard rules are never broken. Starter rules seed memory with common exceptions; CloudSense learns the rest from your team’s reviews." />
      <div className="flex flex-col gap-5">
        <p className="flex items-center gap-2 text-[15px] font-semibold text-ink"><Lock size={16} /> Hard rules (always enforced)</p>
        <div className="flex flex-col gap-3">
          {Object.keys(hard).map((r) => <Checkbox key={r} checked={hard[r]} onChange={(v) => setHard((h) => ({ ...h, [r]: v }))} title={r} />)}
        </div>
        <div className="flex gap-2">
          <Input value={custom} onChange={(e) => setCustom(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addCustom()}
            placeholder="Add your own rule, e.g. “Never stop anything in the payments VPC”" />
          <button type="button" className="btn h-[39px]" onClick={addCustom} disabled={!custom.trim()}>Add</button>
        </div>
        <div className="h-px bg-rule" />
        <p className="flex items-center gap-2 text-[15px] font-semibold text-ink"><Icon name="sparkles" size={16} className="text-learned" /> Starter rules (common exceptions)</p>
        <div className="grid gap-4 sm:grid-cols-2">
          {STARTER.map(([id, title, desc]) => (
            <Checkbox key={id} checked={starter[id]} onChange={(v) => setStarter((s) => ({ ...s, [id]: v }))} title={title} desc={desc} />
          ))}
        </div>
        <p className="text-[13px] text-muted">CloudSense will learn more rules from your team’s reviews.</p>
      </div>
      <Footer back={back} next={save} busy={busy} skip={next} error={error} />
    </>
  );
}

// ---------- step 6 ----------
function StepSafety({ org, back, done }: { org: OrgInfo; back: () => void; done: (scanId: string | null) => void }) {
  const s = org.settings.safety ?? {};
  const [mode, setMode] = useState<"recommend" | "actions">(s.mode ?? "recommend");
  const [dryRun, setDryRun] = useState(s.dry_run ?? true);
  const [confirm, setConfirm] = useState(s.type_confirm ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const actionUrl = launchUrl(ACTION_TEMPLATE_URL, "cloudsense-action", org);
  const nServices = org.settings.services?.length ?? 6;

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      await put(`/orgs/${ORG}/settings`, { safety: { mode, dry_run: dryRun, type_confirm: confirm }, onboarded: true,
        onboarding_step: 7 });
      const r = await post<{ scan_id: string }>(`/orgs/${ORG}/scans`);
      done(r.scan_id);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  const card = (m: "recommend" | "actions", title: string, desc: string, extra: ReactNode) => (
    <button type="button" onClick={() => setMode(m)} aria-pressed={mode === m}
      className={`flex flex-col gap-2 rounded-xl border p-5 text-left ${mode === m ? "border-approve ring-1 ring-approve" : "border-rule hover:border-muted"}`}>
      <span className="flex items-center gap-2.5">
        <span className={`flex size-[18px] items-center justify-center rounded-full border-2 ${mode === m ? "border-approve" : "border-rule"}`}>
          {mode === m && <span className="size-2 rounded-full bg-approve" />}
        </span>
        <span className="text-[15px] font-semibold text-ink">{title}</span>
      </span>
      <span className="text-[13px] leading-[1.45] text-muted">{desc}</span>
      {extra}
    </button>
  );

  return (
    <>
      <StepHead title="Safety settings" desc="You can change these any time in Settings." />
      <div className="flex flex-col gap-5">
        <div className="grid gap-4 sm:grid-cols-2">
          {card("recommend", "Recommend only", "Suggestions only. Nothing changes in AWS.",
            <span className="w-fit rounded-full bg-track px-2 py-0.5 text-xs font-medium text-muted">Default</span>)}
          {card("actions", "Safe actions", "Approved suggestions can be executed, with backup and undo. Needs the optional action role.",
            actionUrl ? <a href={actionUrl} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
              className="flex w-fit items-center gap-1.5 text-[13px] font-medium text-approve"><ExternalLink size={14} /> Launch action-role stack</a>
              : <span className="text-xs text-muted">Deploy <code>infra/cloudsense-action.yaml</code> to enable.</span>)}
        </div>
        <div className="h-px bg-rule" />
        <Setting title="Dry run" desc="Every action shows the planned AWS calls first and needs a second click.">
          <Toggle label="Dry run" checked={dryRun} onChange={setDryRun} />
        </Setting>
        <Setting title="Type to confirm" desc="Reviewer types the resource name before an action runs.">
          <Toggle label="Type to confirm" checked={confirm} onChange={setConfirm} />
        </Setting>
        <Banner kind="ok" title="You’re ready">
          First scan: {org.accounts.length} account{org.accounts.length === 1 ? "" : "s"} · {nServices} service{nServices === 1 ? "" : "s"} · about 60 seconds.
        </Banner>
      </div>
      <Footer back={back} next={start} nextLabel="Run first scan" busy={busy} error={error} />
    </>
  );
}
