import { useEffect, useState } from "react";
import { api, ORG, post } from "../api";
import { PageState, PageTitle, useLoad } from "../components/ui";

interface OrgResp {
  id: string; name: string; hard_rules: string[]; external_id: string; principal_arn: string; dry_run: boolean;
  accounts: { id: string; alias: string; aws_account_id: string; role_arn: string; regions: string[]; action_role_arn: string | null }[];
}

const TEMPLATE_URL = import.meta.env.VITE_READONLY_TEMPLATE_URL as string | undefined;

function launchStackUrl(o: OrgResp): string | null {
  if (!TEMPLATE_URL) return null;
  const p = new URLSearchParams({ templateURL: TEMPLATE_URL, stackName: "cloudsense-readonly",
    param_ExternalId: o.external_id, param_CloudSensePrincipalArn: o.principal_arn });
  return `https://console.aws.amazon.com/cloudformation/home#/stacks/create/review?${p}`;
}

export default function Settings() {
  const org = useLoad(() => api<OrgResp>(`/orgs/${ORG}`));
  const templates = useLoad(() => api<Record<string, string>>("/templates"));
  return (
    <>
      <PageTitle title="Settings" />
      <PageState loading={org.loading} error={org.error} onRetry={org.reload}>
        {org.data && (
          <div className="space-y-8">
            <p className={`rounded-md border p-3 text-sm ${org.data.dry_run ? "border-approve/50" : "border-reject/60 text-reject"}`}>
              {org.data.dry_run ? "Dry run is on: approved actions show the exact AWS calls but change nothing."
                : "Dry run is off: approved actions change real AWS resources (snapshots are taken first)."}
            </p>
            <Accounts o={org.data} onChange={org.reload} />
            <HardRules initial={org.data.hard_rules} />
            <PageState loading={templates.loading} error={templates.error}>
              {templates.data && <Templates all={templates.data} />}
            </PageState>
          </div>
        )}
      </PageState>
    </>
  );
}

function Section({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-rule bg-panel p-5">
      <h2 className="font-semibold">{title}</h2>
      <p className="mb-4 mt-1 max-w-2xl text-sm text-muted">{hint}</p>
      {children}
    </section>
  );
}

function Accounts({ o, onChange }: { o: OrgResp; onChange: () => void }) {
  const [form, setForm] = useState({ alias: "", aws_account_id: "", role_arn: "", regions: "us-east-1" });
  const [msg, setMsg] = useState<string | null>(null);
  const url = launchStackUrl(o);
  const connect = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await post(`/orgs/${ORG}/accounts`, { ...form, regions: form.regions.split(",").map((r) => r.trim()).filter(Boolean) });
      setMsg(`Connected ${form.alias}.`);
      onChange();
    } catch (err) {
      setMsg(`Couldn't connect: ${(err as Error).message}`);
    }
  };
  return (
    <Section title="AWS accounts" hint="CloudSense reads your account through a read-only role you create. It stores the role ARN, never keys.">
      <ol className="mb-4 list-decimal space-y-1 pl-5 text-sm">
        <li>Create the read-only role with ExternalId <code className="rounded bg-paper px-1">{o.external_id}</code>
          {url ? <> using <a className="underline" href={url} target="_blank" rel="noreferrer">Launch Stack</a>.</>
            : <> using <code className="rounded bg-paper px-1">infra/cloudsense-readonly.yaml</code> (set VITE_READONLY_TEMPLATE_URL for a one-click link).</>}</li>
        <li>Paste the RoleArn output below.</li>
      </ol>
      {o.accounts.length > 0 && (
        <ul className="mb-4 space-y-1 text-sm">
          {o.accounts.map((a) => (
            <li key={a.id}><span className="font-medium">{a.alias}</span> <span className="text-muted">{a.aws_account_id}, {a.regions.join(", ")}{a.action_role_arn ? ", actions enabled" : ", read-only"}</span></li>
          ))}
        </ul>
      )}
      <form onSubmit={connect} className="grid gap-3 sm:grid-cols-2">
        {([["alias", "Name", "prod"], ["aws_account_id", "AWS account ID", "123456789012"],
           ["role_arn", "Role ARN", "arn:aws:iam::123456789012:role/CloudSenseReadOnlyRole"], ["regions", "Regions (comma separated)", "us-east-1"]] as const).map(([k, l, ph]) => (
          <label key={k} className="text-sm">{l}
            <input className="field mt-1" required value={form[k]} placeholder={ph} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
          </label>
        ))}
        <div className="sm:col-span-2"><button className="btn btn-approve">Connect account</button>
          {msg && <span className="ml-3 text-sm" role="status">{msg}</span>}</div>
      </form>
    </Section>
  );
}

function HardRules({ initial }: { initial: string[] }) {
  const [text, setText] = useState(initial.join("\n"));
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => setText(initial.join("\n")), [initial]);
  const save = async () => {
    try {
      await api(`/orgs/${ORG}/hard_rules`, { method: "PUT", body: JSON.stringify({ rules: text.split("\n") }) });
      setMsg("Saved. The agent follows these on the next scan.");
    } catch (e) {
      setMsg(`Couldn't save: ${(e as Error).message}`);
    }
  };
  return (
    <Section title="Hard rules" hint="Written rules the agent never breaks, one per line. They always win over learned rules.">
      <textarea className="field" rows={4} value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Never touch prod RDS" />
      <div className="mt-2"><button className="btn" onClick={save}>Save hard rules</button>
        {msg && <span className="ml-3 text-sm" role="status">{msg}</span>}</div>
    </Section>
  );
}

function Templates({ all }: { all: Record<string, string> }) {
  const [picked, setPicked] = useState<string[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const accept = async () => {
    try {
      const r = await post<{ accepted: string[] }>(`/orgs/${ORG}/templates`, { rule_ids: picked });
      setMsg(`Added ${r.accepted.length} rule${r.accepted.length === 1 ? "" : "s"} to memory.`);
    } catch (e) {
      setMsg(`Couldn't add them: ${(e as Error).message}`);
    }
  };
  return (
    <Section title="Starter rules" hint="Common exceptions most teams share. Pick the ones that are true for you so the first scan is already sensible.">
      <ul className="space-y-2">
        {Object.entries(all).map(([id, text]) => (
          <li key={id}>
            <label className="flex gap-3 text-sm">
              <input type="checkbox" className="mt-1" checked={picked.includes(id)}
                onChange={(e) => setPicked(e.target.checked ? [...picked, id] : picked.filter((p) => p !== id))} />
              <span className="font-voice italic">{text}</span>
            </label>
          </li>
        ))}
      </ul>
      <div className="mt-3"><button className="btn" onClick={accept} disabled={!picked.length}>Add {picked.length || ""} to memory</button>
        {msg && <span className="ml-3 text-sm" role="status">{msg}</span>}</div>
    </Section>
  );
}
