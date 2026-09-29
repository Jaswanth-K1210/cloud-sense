const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";
const TOKEN_KEY = "cloudsense.token";

/** The signed-in user's workspace id. A live binding: set after login, read by every page at call time. */
export let ORG = "";
export function setOrg(id: string): void {
  ORG = id;
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode: the session lasts for this page load only */
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401 && token) {
      setToken(null);
      window.dispatchEvent(new Event("cloudsense:logout")); // session expired: back to login
    }
    if (Array.isArray(detail)) detail = (detail as { msg: string }[]).map((d) => d.msg.replace(/^Value error, /, "")).join("; ");
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const put = <T>(path: string, body: unknown) => api<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const patch = <T>(path: string, body: unknown) => api<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

// ---- shapes returned by backend/api/routes.py ----

export interface MemoryHit { id: string; text: string; type?: string | null; score?: number | null }
export interface AgentDecision {
  decision: "recommend" | "suppress" | "ask";
  action: string; confidence: number; predicted_approval: number; reason: string;
  cited_memory_ids: string[]; risk_note: string; memories?: MemoryHit[];
}
export interface Candidate {
  id: string; scan_id: string; rule_id: string; action: string; monthly_saving: number | null;
  signals_text: string; blast_radius: { count: number; names: string[] }; status: string;
  agent: AgentDecision; reversible?: boolean; warnings?: string[];
  resource: { id: string; name: string; type: string; tags: Record<string, string>; owner_team: string | null;
    account?: string | null; instance_type?: string | null; size_gb?: number | null; created_at?: string | null;
    state?: string | null; metrics?: { cpu_avg?: number | null; cpu_max?: number | null; cpu_p95?: number | null;
      net_in_mb_per_day?: number | null; net_out_mb_per_day?: number | null; db_connections_max?: number | null;
      daily_cpu_series?: number[] };
    role_hints: string[]; iac_managed: boolean; region: string };
}
export interface ScanDetail {
  id: string; status: string; started_at: string; finished_at: string | null; resource_count: number;
  candidate_count: number; errors: Record<string, string>[]; progress?: ScanProgress;
  recommended: Candidate[]; asked: Candidate[]; suppressed: Candidate[]; reviewed: Candidate[];
}
export interface ScanProgress { step?: number; account?: string; counts?: Record<string, number> }
export interface ScanSummary { id: string; status: string; started_at: string; resource_count: number;
  candidate_count: number; progress?: ScanProgress }
export interface Verdict {
  id: string; decision: string; reason: string; scope: string; learning_status: string;
  learned_rule: { id: string; text: string; proof_count: number } | null;
}
export interface Rule { id: string; text: string; proof_count: number; tags: string[]; sources: MemoryHit[]; updated_at?: string | null }
export interface Metrics {
  series: { scan_id: string; started_at: string; approved: number; rejected: number; shown: number;
    suppressed: number; acceptance_rate: number | null; found: number; rules_learned: number }[];
  savings: { found: number; approved: number; executed: number; approved_count: number; executed_count: number };
}
export interface User { id: string; name: string; role: string; email?: string; slack_id?: string | null }
export interface OrgSettings {
  onboarding_step?: number; onboarded?: boolean; services?: string[]; schedule?: "daily" | "weekly" | "manual";
  profile?: { role?: string | null; team_size?: string | null; spend?: string | null };
  slack?: { channel?: string; weekly_summary?: boolean };
  safety?: { mode?: "recommend" | "actions"; dry_run?: boolean; type_confirm?: boolean };
}
export interface Me { user: User & { email: string }; org: { id: string; name: string; settings: OrgSettings } }
export interface OrgInfo {
  id: string; name: string; hard_rules: string[]; external_id: string; principal_arn: string; dry_run: boolean;
  settings: OrgSettings;
  accounts: { id: string; alias: string; aws_account_id: string; role_arn: string; regions: string[];
    action_role_arn: string | null }[];
}
export interface Action { id: string; kind: string; status: string; api_calls: { service: string; op: string; params: unknown }[];
  undo_handle: Record<string, unknown> }

export const money = (n: number | null | undefined) =>
  `$${(n ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

/** The readable part of a retained verdict: what was proposed and the engineer's reason. */
export function memoryParts(text: string): { proposal: string | null; reason: string | null; raw: string } {
  const lines = text.split("\n").map((l) => l.trim());
  const proposal = lines.find((l) => l.startsWith("CloudSense proposed:"))?.replace("CloudSense proposed: ", "") ?? null;
  const verdict = lines.find((l) => l.startsWith("Verdict:"));
  const reason = verdict?.split("Reason: ")[1] ?? null;
  return { proposal, reason, raw: text };
}
