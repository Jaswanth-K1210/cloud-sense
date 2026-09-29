import { api, ORG } from "../api";
import { relTime } from "../components/Shell";
import { PageState, PageTitle, useLoad } from "../components/ui";

interface Event { id: string; at: string; actor: string; event: string; details: Record<string, unknown> }

const LABEL: Record<string, (d: Record<string, unknown>) => string> = {
  verdict: (d) => `${d.decision === "reject" ? "Rejected" : d.decision === "approve" ? "Approved" : "Snoozed"} a recommendation${d.reason ? `: “${d.reason}”` : ""}`,
  action_executed: (d) => `Executed ${d.kind}${(d.snapshot_ids as string[] | undefined)?.length ? ` (backup ${(d.snapshot_ids as string[]).join(", ")})` : ""}`,
  action_dry_run: (d) => `Dry run of ${d.kind}`,
  action_undone: () => "Undid an action",
  iac_diff: () => "Generated a Terraform change instead of acting",
  reminder: (d) => String(d.text ?? "Reminder"),
  account_connected: (d) => `Connected AWS account ${d.alias}`,
  hard_rules_updated: () => "Updated hard rules",
  templates_accepted: (d) => `Added starter rules: ${(d.rule_ids as string[] | undefined)?.join(", ")}`,
  rule_deleted: () => "Deleted a learned rule",
  signed_up: () => "Created the workspace",
  workspace_updated: (d) => `Updated company details${d.name ? ` (${d.name})` : ""}`,
  settings_updated: (d) => `Changed settings: ${Object.keys(d).filter((k) => k !== "onboarding_step").join(", ").replace("onboarded", "finished setup")}`,
  account_updated: (d) => `Updated AWS account ${d.alias ?? ""}`.trim(),
  account_removed: (d) => `Removed AWS account ${d.alias ?? ""}`.trim(),
  member_updated: (d) => `Updated team member ${d.member ?? ""}${d.role ? ` (role: ${d.role})` : ""}`,
  password_changed: () => "Changed their password",
};

export default function Activity() {
  const rows = useLoad(() => api<Event[]>(`/orgs/${ORG}/activity`));
  return (
    <>
      <PageTitle title="Activity" subtitle="Every review, action and settings change, newest first." />
      <PageState loading={rows.loading} error={rows.error} onRetry={rows.reload}
        empty={rows.data?.length === 0 && "Nothing yet. Reviews, actions and settings changes appear here."}>
        <ol className="card divide-y divide-rule">
          {(rows.data ?? []).map((e) => (
            <li key={e.id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-5 py-3">
              <span className="w-20 shrink-0 text-xs text-muted" title={new Date(e.at).toLocaleString()}>{relTime(e.at)}</span>
              <span className="w-36 shrink-0 text-sm font-medium text-ink">{e.actor}</span>
              <span className="min-w-0 flex-1 text-sm text-ink">{(LABEL[e.event] ?? (() => e.event))(e.details)}</span>
            </li>
          ))}
        </ol>
      </PageState>
    </>
  );
}
