import { Check, Cloud, Download, Inbox, Lock, RefreshCw, Trash2, Undo2, X, type LucideIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { api, ORG, post } from "../api";
import { Icon } from "../components/Icon";
import { Banner } from "../components/form";
import { FilterSelect } from "../components/bits";
import { TopBar } from "../components/Shell";
import { PageState, useLoad } from "../components/ui";

interface Event { id: string; at: string; actor: string; event: string; details: Record<string, unknown> }
type D = Record<string, unknown>;
const list = (v: unknown) => (Array.isArray(v) ? (v as string[]).join(", ") : "");

/** event -> [icon, title, detail line] */
const RENDER: Record<string, (d: D) => [LucideIcon | "sparkles" | "act", string, string]> = {
  action_executed: (d) => ["act", `Executed ${d.kind}`, list(d.snapshot_ids) ? `Snapshot ${list(d.snapshot_ids)} created first` : ""],
  action_dry_run: (d) => [Check, `Dry run of ${d.kind}`, "Planned AWS calls only; nothing changed"],
  action_undone: () => [Undo2, "Undo", "Reverted an earlier action"],
  iac_diff: () => [Check, "Generated a Terraform change", "Terraform-managed resources get a code diff"],
  reminder: (d) => [RefreshCw, "Reminder", String(d.text ?? "")],
  verdict: (d) => d.decision === "reject" ? [X, "Rejected a recommendation", d.reason ? `“${d.reason}”` : ""]
    : d.decision === "approve" ? [Check, "Approved a recommendation", ""] : [RefreshCw, "Snoozed a recommendation", "For 30 days"],
  rule_learned: (d) => ["sparkles", `Rule learned: ${d.text}${d.proof_count ? ` (confirmed ${d.proof_count}×)` : ""}`, d.from ? `From ${d.from}’s rejection` : ""],
  rule_deleted: () => [Trash2, "Rule deleted", ""],
  rule_reported: (d) => [X, "Rule reported as wrong", String(d.reason ?? "")],
  override: (d) => [RefreshCw, `Override: recommended ${d.resource ?? "a skipped resource"} anyway`, ""],
  scan_started: (d) => [RefreshCw, `Scan started (${d.trigger ?? "manual"})`, "All accounts"],
  scan_finished: (d) => [Inbox, `Scan finished: ${d.resources} resources · ${d.recommendations} recommendations · ${d.skipped} skipped`, list(d.accounts)],
  scan_failed: (d) => [X, "Scan failed", `${d.errors} error(s) · ${list(d.accounts)}`],
  account_connected: (d) => [Cloud, `Account connected: ${d.alias} (read-only)`, ""],
  account_updated: (d) => [Cloud, `Account updated: ${d.alias}`, ""],
  account_removed: (d) => [Trash2, `Account removed: ${d.alias}`, ""],
  hard_rules_updated: (d) => [Lock, "Hard rules updated", list(d.rules)],
  templates_accepted: (d) => ["sparkles", "Starter rules added", list(d.rule_ids)],
  signed_up: () => [Cloud, "Workspace created", ""],
  workspace_updated: (d) => [Cloud, "Company details updated", String(d.name ?? "")],
  settings_updated: (d) => [RefreshCw, "Settings changed", Object.keys(d).filter((k) => k !== "onboarding_step").join(", ").replace("onboarded", "finished setup")],
  member_updated: (d) => [Check, `Team member updated: ${d.member ?? ""}`, d.role ? `Role: ${d.role}` : ""],
  password_changed: () => [Lock, "Password changed", ""],
};

function time(iso: string): string {
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  const days = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 864e5);
  const t = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return days === 0 ? t : days === 1 ? `Yesterday ${t}` : d.toLocaleDateString([], { month: "short", day: "numeric" });
}
const GROUP: Record<string, string> = { verdict: "Reviews", rule_learned: "Learning", rule_deleted: "Learning", rule_reported: "Learning",
  action_executed: "Actions", action_dry_run: "Actions", action_undone: "Actions", iac_diff: "Actions", scan_started: "Scans",
  scan_finished: "Scans", scan_failed: "Scans" };

/** Figma 20: audit trail. */
export default function Activity() {
  const rows = useLoad(() => api<Event[]>(`/orgs/${ORG}/activity?limit=500`));
  const [user, setUser] = useState("all");
  const [kind, setKind] = useState("all");
  const [range, setRange] = useState("7");
  const [msg, setMsg] = useState<string | null>(null);
  const users = useMemo(() => [...new Set((rows.data ?? []).map((e) => e.actor))].sort(), [rows.data]);
  const shown = (rows.data ?? []).filter((e) => (user === "all" || e.actor === user)
    && (kind === "all" || (GROUP[e.event] ?? "Settings") === kind)
    && (range === "all" || Date.now() - new Date(e.at.endsWith("Z") || e.at.includes("+") ? e.at : `${e.at}Z`).getTime() < Number(range) * 864e5));

  const exportCsv = () => {
    const esc = (v: string) => `"${v.replace(/"/g, '""')}"`;
    const csv = ["time,who,event,detail", ...shown.map((e) => {
      const [, title, sub] = (RENDER[e.event] ?? (() => [Check, e.event, ""]))(e.details);
      return [e.at, e.actor, title, sub].map((v) => esc(String(v))).join(",");
    })].join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "cloudsense-activity.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const undo = async (actionId: string) => {
    try {
      await post(`/actions/${actionId}/undo`);
      setMsg("Undone.");
      rows.reload();
    } catch (e) {
      setMsg((e as Error).message);
    }
  };

  return (
    <>
      <TopBar title="Activity" subtitle="Every scan, review, action and settings change, with who did it." />
      {msg && <Banner kind="info" title={msg} />}
      <div className="flex flex-wrap items-center gap-2.5">
        <FilterSelect label="User" value={user} onChange={setUser} options={[["all", "User: All"], ...users.map((u) => [u, u] as [string, string])]} />
        <FilterSelect label="Event" value={kind} onChange={setKind} options={[["all", "Event: All"], ...["Scans", "Reviews", "Learning", "Actions", "Settings"].map((k) => [k, k] as [string, string])]} />
        <FilterSelect label="Date range" value={range} onChange={setRange} options={[["1", "Last 24 hours"], ["7", "Last 7 days"], ["30", "Last 30 days"], ["all", "All time"]]} />
        <span className="flex-1" />
        <button className="btn h-[31px]" onClick={exportCsv} disabled={!shown.length}><Download size={14} /> Export CSV</button>
      </div>
      <PageState loading={rows.loading && !rows.data} error={rows.error} onRetry={rows.reload}
        empty={rows.data && shown.length === 0 && "Nothing in this range. Scans, reviews, actions and settings changes appear here."}>
        <ol className="card divide-y divide-rule">
          {shown.map((e) => {
            const [I, title, sub] = (RENDER[e.event] ?? (() => [Check, e.event, ""]))(e.details);
            const actionId = e.event === "action_executed" ? String(e.details.action_id ?? "") : "";
            return (
              <li key={e.id} className="flex items-start gap-4 px-5 py-3.5">
                <span className="w-24 shrink-0 pt-px text-[13px] text-muted" title={new Date(e.at).toLocaleString()}>{time(e.at)}</span>
                <span className={`mt-0.5 ${I === "sparkles" ? "text-learned" : "text-muted"}`}>
                  {I === "sparkles" ? <Icon name="sparkles" size={15} /> : I === "act" ? <Icon name="act" size={15} /> : <I size={15} />}
                </span>
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <p className="text-sm font-medium text-ink">{title}</p>
                  <p className="text-[13px] text-muted">{[e.actor, sub].filter(Boolean).join(" · ")}</p>
                </div>
                {actionId && <button className="btn h-[31px]" onClick={() => undo(actionId)}>Undo</button>}
              </li>
            );
          })}
        </ol>
      </PageState>
    </>
  );
}
