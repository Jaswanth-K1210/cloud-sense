import { Box, Database, Globe, HardDrive, Server, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** Figma "Sparkline": 14 daily bars (5px wide). */
export function Sparkline({ values, height = 28, width = 96, highlightMax = false }: {
  values: number[] | undefined; height?: number; width?: number; highlightMax?: boolean;
}) {
  const v = (values ?? []).slice(-14);
  if (!v.length) return <span className="text-xs text-muted">No usage data</span>;
  const max = Math.max(1, ...v);
  return (
    <span className="flex items-end gap-[2px]" style={{ height, width }} role="img"
      aria-label={`Daily CPU, last ${v.length} days: ${v.map((x) => `${Math.round(x)}%`).join(", ")}`}>
      {v.map((x, i) => (
        <span key={i} className={`w-[5px] rounded-sm ${highlightMax && x === max && max > 20 ? "bg-warn" : "bg-approve-soft"}`}
          style={{ height: Math.max(2, (x / Math.max(max, 20)) * height) }} />
      ))}
    </span>
  );
}

const TYPE_ICON: Record<string, LucideIcon> = { ec2: Server, rds: Database, ebs: HardDrive, snapshot: HardDrive, s3: Box,
  lb: Globe, eip: Globe, target_group: Globe, asg: Server, nat: Globe, eks: Server, opensearch: Database };
export function TypeIcon({ type, size = 20 }: { type: string; size?: number }) {
  const I = TYPE_ICON[type] ?? Server;
  return <I size={size} strokeWidth={1.75} />;
}

export const TYPE_LABEL: Record<string, string> = { ec2: "EC2", rds: "RDS", ebs: "EBS", snapshot: "Snapshot", s3: "S3 bucket",
  eip: "Elastic IP", lb: "Load balancer", target_group: "Target group", asg: "Auto Scaling group", nat: "NAT gateway",
  eks: "EKS", opensearch: "OpenSearch" };

export function Pill({ children, tone = "plain", icon }: { children: ReactNode; tone?: "plain" | "approve" | "learned" | "warn" | "reject" | "success"; icon?: ReactNode }) {
  const c = { plain: "bg-track text-ink", approve: "bg-approve/10 text-approve", learned: "bg-learned-soft text-learned",
    warn: "bg-warn-soft text-warn", reject: "bg-reject/10 text-reject", success: "bg-success/10 text-success" }[tone];
  return <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${c}`}>{icon}{children}</span>;
}

/** Tag chips shown on cards: team:x, env:y. */
export function TagPills({ tags }: { tags: Record<string, string> }) {
  const shown = ["team", "env", "service", "owner"].filter((k) => tags[k]);
  return <>{shown.map((k) => <Pill key={k}>{k}:{tags[k]}</Pill>)}</>;
}

/** Figma "Select": a compact filter dropdown. */
export function FilterSelect({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: [string, string][];
}) {
  return (
    <label className="relative flex h-8 items-center rounded-lg border border-rule bg-panel pl-2.5 pr-1 text-[13px] font-medium text-ink">
      <span className="sr-only">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="h-full cursor-pointer bg-transparent pr-1 outline-none">
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
}

export function Tabs({ tabs, active, onChange }: { tabs: [string, string][]; active: string; onChange: (k: string) => void }) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-rule">
      {tabs.map(([k, label]) => (
        <button key={k} role="tab" aria-selected={active === k} onClick={() => onChange(k)}
          className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${active === k ? "border-approve text-ink" : "border-transparent text-muted hover:text-ink"}`}>
          {label}
        </button>
      ))}
    </div>
  );
}

export function quoteParts(text: string): { who: string | null; when: string | null; reason: string | null; proposal: string | null } {
  const who = text.match(/Reviewer (.+?) \(/)?.[1] ?? null;
  const iso = text.match(/ at (\d{4}-\d{2}-\d{2}T[\d:.]+(?:[+-]\d{2}:\d{2}|Z)?)/)?.[1];
  const when = iso ? new Date(iso).toLocaleDateString([], { month: "short", day: "numeric" }) : null;
  const reason = text.match(/Reason: (.+)/)?.[1]?.trim() ?? null;
  const raw = text.match(/CloudSense proposed: (.+?) \(/)?.[1] ?? null;
  const verb: Record<string, string> = { stop: "stop", rightsize: "rightsize", snapshot_delete: "delete", modify_gp3: "switch to gp3",
    release: "release", delete_snapshot: "delete snapshot", s3_lifecycle: "add a lifecycle rule to" };
  const proposal = raw ? raw.replace(/^(\w+) on /, (_, a: string) => `${verb[a] ?? a} `) : null;
  return { who, when, reason, proposal };
}
