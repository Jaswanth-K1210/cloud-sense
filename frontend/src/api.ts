const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";
export const ORG = (import.meta.env.VITE_ORG_ID as string | undefined) ?? "acme";
const USER_KEY = "cloudsense.user";

export function currentUserId(): string {
  try {
    return localStorage.getItem(USER_KEY) ?? "u-reviewer";
  } catch {
    return "u-reviewer";
  }
}

export function setCurrentUserId(id: string): void {
  try {
    localStorage.setItem(USER_KEY, id);
  } catch {
    /* private mode: picker still works for this page load */
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", "X-User-Id": currentUserId(), ...(init.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

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
    account?: string | null;
    role_hints: string[]; iac_managed: boolean; region: string };
}
export interface ScanDetail {
  id: string; status: string; started_at: string; finished_at: string | null; resource_count: number;
  candidate_count: number; errors: Record<string, string>[];
  recommended: Candidate[]; asked: Candidate[]; suppressed: Candidate[]; reviewed: Candidate[];
}
export interface ScanSummary { id: string; status: string; started_at: string; resource_count: number; candidate_count: number }
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
export interface User { id: string; name: string; role: string }
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
