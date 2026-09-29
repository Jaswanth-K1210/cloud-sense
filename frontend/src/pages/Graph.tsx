import { Background, Controls, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import { api, money, ORG, post, type Candidate, type ScanSummary } from "../api";
import { Icon } from "../components/Icon";
import { Banner } from "../components/form";
import { FilterSelect, Pill, Sparkline, TagPills, TYPE_LABEL, TypeIcon } from "../components/bits";
import { TopBar, useShell } from "../components/Shell";
import { PageState, useLoad } from "../components/ui";
import { RejectModal } from "./Queue";

interface GNode {
  id: string; type: string; name: string; status: string | null; candidate_id: string | null; action: string | null;
  saving: number | null; role_hints: string[]; blast_radius: { count: number; ids: string[] }; tags: Record<string, string>;
  account: string | null; region: string | null; state: string | null; instance_type: string | null;
  metrics: { cpu_avg?: number; db_connections_max?: number; net_in_mb_per_day?: number; daily_cpu_series?: number[] };
  attrs: { replica_source?: string; db_role?: string };
}
interface GData { nodes: GNode[]; edges: { source: string; target: string }[] }

// Legend (Figma 16): recommended · skipped (protected) · stopped by CloudSense · normal
const DOT: Record<string, string> = { pending: "#b91c1c", asked: "#b45309", suppressed: "#6d28d9", executed: "#0c1a17",
  approved: "#0f766e", rejected: "#9aa6a2", snoozed: "#9aa6a2" };
const DOT_NORMAL = "#c7d0cd";

function subtitle(n: GNode): string {
  if (n.type === "rds") return n.attrs.replica_source || n.attrs.db_role === "replica" ? "RDS read replica" : "RDS primary";
  if (n.type === "ebs") return `EBS · ${n.state === "available" ? "unattached" : "attached"}`;
  if (n.type === "ec2") return [TYPE_LABEL.ec2, n.state === "stopped" ? "stopped" : n.instance_type].filter(Boolean).join(" · ");
  return TYPE_LABEL[n.type] ?? n.type;
}

type RNodeData = { n: GNode; dim: boolean; hit: boolean; selected: boolean };
function ResourceNode({ data }: NodeProps<Node<RNodeData>>) {
  const { n, dim, hit, selected } = data;
  return (
    <div className={`flex items-center gap-2 rounded-lg border bg-panel px-3 py-2 shadow-sm transition-opacity ${selected ? "border-approve ring-2 ring-approve/30" : hit ? "border-dashed border-reject" : "border-rule"} ${dim ? "opacity-35" : ""}`}>
      <Handle type="target" position={Position.Left} className="!size-1 !border-0 !bg-transparent" />
      <span className="text-muted"><TypeIcon type={n.type} size={14} /></span>
      <span className="flex flex-col">
        <span className="whitespace-nowrap text-[13px] font-semibold text-ink">{n.name}</span>
        <span className="whitespace-nowrap text-[11px] text-muted">{subtitle(n)}</span>
      </span>
      <span className="ml-1 size-2 rounded-full" style={{ background: n.status ? DOT[n.status] : DOT_NORMAL }} />
      <Handle type="source" position={Position.Right} className="!size-1 !border-0 !bg-transparent" />
    </div>
  );
}
const nodeTypes = { resource: ResourceNode };

function layout(nodes: GNode[], edges: GData["edges"]): Record<string, { x: number; y: number }> {
  const deps: Record<string, string[]> = {};
  edges.forEach((e) => (deps[e.source] ??= []).push(e.target));
  const level: Record<string, number> = {};
  const depth = (id: string, seen = new Set<string>()): number => {
    if (id in level) return level[id];
    if (seen.has(id)) return 0;
    seen.add(id);
    level[id] = Math.max(-1, ...(deps[id] ?? []).map((d) => depth(d, seen))) + 1;
    return level[id];
  };
  nodes.forEach((n) => depth(n.id));
  const rows: Record<number, number> = {};
  return Object.fromEntries(nodes.map((n) => {
    const l = level[n.id] ?? 0;
    rows[l] = (rows[l] ?? 0) + 1;
    return [n.id, { x: l * 250, y: (rows[l] - 1) * 72 }];
  }));
}

async function latestGraph(): Promise<GData | null> {
  const scans = await api<ScanSummary[]>(`/orgs/${ORG}/scans`);
  const done = scans.find((s) => s.status === "done");
  return done ? api<GData>(`/graph/${done.id}`) : null;
}

export default function Graph() {
  const shell = useShell();
  const g = useLoad(latestGraph, [shell.lastScan?.id, shell.lastScan?.status]);
  const [selected, setSelected] = useState<string | null>(null);
  const [account, setAccount] = useState("all");
  const [q, setQ] = useState("");
  const [onlyRecs, setOnlyRecs] = useState(false);
  const [rejecting, setRejecting] = useState<GNode | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const accounts = useMemo(() => [...new Set((g.data?.nodes ?? []).map((n) => n.account).filter(Boolean) as string[])].sort(), [g.data]);
  const visible = useMemo(() => {
    const ns = (g.data?.nodes ?? []).filter((n) => (account === "all" || n.account === account)
      && (!onlyRecs || n.status) && (!q || n.name.toLowerCase().includes(q.toLowerCase())));
    const ids = new Set(ns.map((n) => n.id));
    return { nodes: ns, edges: (g.data?.edges ?? []).filter((e) => ids.has(e.source) && ids.has(e.target)) };
  }, [g.data, account, q, onlyRecs]);
  const sel = g.data?.nodes.find((n) => n.id === selected) ?? null;

  const { nodes, edges } = useMemo(() => {
    const pos = layout(visible.nodes, visible.edges);
    const hit = new Set(sel?.blast_radius.ids ?? []);
    const nodes: Node<RNodeData>[] = visible.nodes.map((n) => ({
      id: n.id, type: "resource", position: pos[n.id],
      data: { n, dim: Boolean(selected) && n.id !== selected && !hit.has(n.id), hit: hit.has(n.id), selected: n.id === selected },
    }));
    const edges: Edge[] = visible.edges.map((e) => {
      const lit = hit.has(e.source) && (e.target === selected || hit.has(e.target));
      return { id: `${e.source}->${e.target}`, source: e.target, target: e.source,
        style: { stroke: lit ? "#b91c1c" : "#c7d0cd", strokeWidth: lit ? 2 : 1.25, strokeDasharray: lit ? "6 4" : undefined } };
    });
    return { nodes, edges };
  }, [visible, sel, selected]);

  const verdict = async (n: GNode, body: Record<string, unknown>) => {
    try {
      await post(`/candidates/${n.candidate_id}/verdict`, body);
      g.reload();
      shell.refresh();
    } catch (e) {
      setFlash((e as Error).message);
    }
  };

  return (
    <>
      <TopBar title="Resource Map" subtitle="What depends on what. Select a resource to see everything that breaks if it goes away." />
      {flash && <Banner kind="err" title={flash} />}
      <PageState loading={g.loading && !g.data} error={g.error} onRetry={g.reload}
        empty={!g.data && "No finished scan yet. Click Scan now to map your resources."}>
        <div className="flex flex-wrap items-center gap-2.5">
          <FilterSelect label="Account" value={account} onChange={setAccount} options={[["all", "Account: All"], ...accounts.map((a) => [a, `Account: ${a}`] as [string, string])]} />
          <label className="relative flex h-[39px] w-56 items-center">
            <Search size={16} className="absolute left-3 text-muted" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search resources" aria-label="Search resources"
              className="h-full w-full rounded-lg border border-rule bg-panel pl-9 pr-3 text-sm focus:border-approve focus:outline-none" />
          </label>
          <label className="flex items-center gap-2 text-[13px] text-ink"><input type="checkbox" className="accent-approve" checked={onlyRecs} onChange={(e) => setOnlyRecs(e.target.checked)} /> Only resources with recommendations</label>
          <span className="flex-1" />
          {[["pending", "Recommended"], ["suppressed", "Skipped (protected)"], ["executed", "Stopped by CloudSense"]].map(([k, l]) => (
            <span key={k} className="flex items-center gap-1.5 text-xs text-muted"><span className="size-[9px] rounded-full" style={{ background: DOT[k] }} />{l}</span>
          ))}
          <span className="flex items-center gap-1.5 text-xs text-muted"><span className="size-[9px] rounded-full" style={{ background: DOT_NORMAL }} />Normal</span>
        </div>
        <div className="flex flex-wrap items-start gap-5">
          <div className="card relative h-[720px] min-w-[360px] flex-1 overflow-hidden">
            <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView nodesDraggable={false} minZoom={0.2}
              onNodeClick={(_, n) => setSelected(n.id === selected ? null : n.id)} onPaneClick={() => setSelected(null)}
              proOptions={{ hideAttribution: true }}>
              <Background color="#e1e7e5" gap={24} />
              <Controls showInteractive={false} />
            </ReactFlow>
            <span className="absolute bottom-3 left-14 rounded-md bg-panel/90 px-2.5 py-1.5 text-xs text-muted shadow-sm">
              {g.data?.nodes.length ?? 0} resources · {visible.nodes.length} shown · dashed = blast radius
            </span>
          </div>
          <aside className="card flex w-full flex-col gap-4 p-5 lg:w-[380px]" aria-live="polite">
            {!sel ? (
              <p className="text-sm text-muted">Select a resource to see its usage, what depends on it, and any open recommendation.</p>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <span className="text-ink"><TypeIcon type={sel.type} size={18} /></span>
                  <h2 className="flex-1 truncate text-[17px] font-semibold text-ink">{sel.name}</h2>
                  <button aria-label="Close" className="text-muted hover:text-ink" onClick={() => setSelected(null)}><X size={16} /></button>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <Pill>{subtitle(sel)}</Pill>
                  {sel.instance_type && sel.type !== "ec2" && <Pill>{sel.instance_type}</Pill>}
                  <TagPills tags={sel.tags} />
                </div>
                <div className="flex flex-col gap-2">
                  <p className="text-[13px] font-medium text-ink">Usage, last 14 days</p>
                  <Sparkline values={sel.metrics.daily_cpu_series} height={40} width={200} />
                  <p className="text-xs text-muted">
                    {[sel.metrics.cpu_avg != null && `CPU avg ${sel.metrics.cpu_avg.toFixed(1)}%`,
                      sel.metrics.db_connections_max != null && `connections ${sel.metrics.db_connections_max}`,
                      sel.metrics.net_in_mb_per_day != null && `network ${Math.round(sel.metrics.net_in_mb_per_day)} MB/day`].filter(Boolean).join(" · ") || "No usage metrics for this resource"}
                  </p>
                </div>
                {sel.blast_radius.count
                  ? <Banner kind="warn" title={`Blast radius: ${sel.blast_radius.count} dependent${sel.blast_radius.count === 1 ? "" : "s"}`}>
                      {sel.blast_radius.ids.map((id) => g.data!.nodes.find((n) => n.id === id)?.name ?? id).join(", ")}. Removing this breaks them.
                    </Banner>
                  : <Banner kind="ok" title="Blast radius: 0">Nothing depends on this resource.</Banner>}
                {sel.candidate_id && (
                  <div className="flex flex-col gap-3 rounded-xl border border-rule p-4">
                    <p className="text-xs text-muted">{sel.status === "suppressed" ? "Skipped recommendation" : "Open recommendation"}</p>
                    <p className="text-sm font-semibold text-ink">{sel.action} · {money(sel.saving)}/mo</p>
                    {(sel.status === "pending" || sel.status === "asked") ? (
                      <div className="flex gap-2">
                        <button className="btn btn-approve h-[29px]" onClick={() => verdict(sel, { decision: "approve" })}>Approve</button>
                        <button className="btn btn-reject h-[29px]" onClick={() => setRejecting(sel)}>Reject</button>
                      </div>
                    ) : <Pill tone={sel.status === "suppressed" ? "learned" : "plain"}>{sel.status}</Pill>}
                  </div>
                )}
                <div className="flex flex-col gap-1.5">
                  <p className="text-[13px] font-medium text-ink">Rules that apply</p>
                  <p className="text-[13px] text-muted">
                    {sel.status === "suppressed" ? <a href="#rules" className="text-approve">A learned or hard rule protects this resource. View rules</a>
                      : "None yet. If you reject, CloudSense will learn why and apply it to look-alikes."}
                  </p>
                </div>
                <p className="flex items-center gap-1.5 text-xs text-muted"><Icon name="net" size={12} /> Role hints: {sel.role_hints.join(", ") || "none"}</p>
              </>
            )}
          </aside>
        </div>
      </PageState>
      {rejecting && (
        <RejectModal c={{ id: rejecting.candidate_id!, resource: { name: rejecting.name } } as unknown as Candidate}
          onClose={() => setRejecting(null)} onSubmit={(body) => { verdict(rejecting, body); setRejecting(null); }} />
      )}
    </>
  );
}
