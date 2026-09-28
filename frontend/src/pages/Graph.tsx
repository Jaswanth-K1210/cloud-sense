import { useMemo, useState } from "react";
import { Background, Controls, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api, ORG, type ScanSummary } from "../api";
import { PageState, PageTitle, StatusTag, useLoad } from "../components/ui";

interface GNode { id: string; type: string; name: string; status: string | null; action: string | null;
  role_hints: string[]; blast_radius: { count: number; ids: string[] } }
interface GData { nodes: GNode[]; edges: { source: string; target: string }[] }

const COLOR: Record<string, string> = {
  pending: "var(--ink)", asked: "var(--learned)", suppressed: "var(--learned)", approved: "var(--approve)",
  executed: "var(--approve)", rejected: "var(--reject)", snoozed: "var(--muted)",
};

/** Dependencies on the left, dependents to the right. */
function layout(g: GData): Record<string, { x: number; y: number }> {
  const deps: Record<string, string[]> = {};
  g.edges.forEach((e) => (deps[e.source] ??= []).push(e.target));
  const level: Record<string, number> = {};
  const depth = (id: string, seen = new Set<string>()): number => {
    if (id in level) return level[id];
    if (seen.has(id)) return 0; // cycle guard
    seen.add(id);
    level[id] = Math.max(-1, ...(deps[id] ?? []).map((d) => depth(d, seen))) + 1;
    return level[id];
  };
  g.nodes.forEach((n) => depth(n.id));
  const rows: Record<number, number> = {};
  return Object.fromEntries(g.nodes.map((n) => {
    const l = level[n.id] ?? 0;
    rows[l] = (rows[l] ?? 0) + 1;
    return [n.id, { x: l * 260, y: (rows[l] - 1) * 76 }];
  }));
}

async function latestGraph(): Promise<{ scan: ScanSummary; graph: GData } | null> {
  const scans = await api<ScanSummary[]>(`/orgs/${ORG}/scans`);
  const done = scans.find((s) => s.status === "done");
  return done ? { scan: done, graph: await api<GData>(`/graph/${done.id}`) } : null;
}

export default function Graph() {
  const g = useLoad(latestGraph);
  const [selected, setSelected] = useState<string | null>(null);

  const { nodes, edges, sel } = useMemo(() => {
    if (!g.data) return { nodes: [] as Node[], edges: [] as Edge[], sel: null as GNode | null };
    const data = g.data.graph;
    const pos = layout(data);
    const sel = data.nodes.find((n) => n.id === selected) ?? null;
    const hit = new Set(sel?.blast_radius.ids ?? []);
    const nodes: Node[] = data.nodes.map((n) => {
      const c = n.status ? COLOR[n.status] : "var(--rule)";
      const lit = n.id === selected || hit.has(n.id);
      return {
        id: n.id, position: pos[n.id], data: { label: `${n.name}\n${n.type}` },
        style: {
          whiteSpace: "pre-line", fontSize: 12, width: 200, borderRadius: 6,
          background: hit.has(n.id) ? "rgb(var(--reject) / 0.12)" : "rgb(var(--panel))", color: "rgb(var(--ink))",
          border: `${n.status ? 2 : 1}px solid rgb(${c})`,
          opacity: selected && !lit ? 0.35 : 1, boxShadow: n.id === selected ? "0 0 0 3px rgb(var(--focus))" : "none",
        },
      };
    });
    const edges: Edge[] = data.edges.map((e) => ({
      id: `${e.source}->${e.target}`, source: e.target, target: e.source,
      style: { stroke: hit.has(e.source) || e.target === selected ? "rgb(var(--reject))" : "rgb(var(--muted))" },
    }));
    return { nodes, edges, sel };
  }, [g.data, selected]);

  return (
    <>
      <PageTitle title="Dependency graph" />
      <PageState loading={g.loading} error={g.error} onRetry={g.reload}
        empty={!g.data && "No finished scan yet. Run a scan to see how your resources connect."}>
        <p className="mb-3 text-sm text-muted">Arrows point from a resource to what depends on it. Select a resource to see everything that breaks if it goes away.</p>
        <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
          <div className="h-[560px] overflow-hidden rounded-lg border border-rule bg-panel">
            <ReactFlow nodes={nodes} edges={edges} fitView nodesDraggable={false}
              onNodeClick={(_, n) => setSelected(n.id === selected ? null : n.id)} onPaneClick={() => setSelected(null)}
              proOptions={{ hideAttribution: true }}>
              <Background color="rgb(var(--rule))" gap={24} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
          <aside className="rounded-lg border border-rule bg-panel p-4 text-sm">
            {sel ? (
              <>
                <p className="text-base font-semibold">{sel.name}</p>
                <p className="text-muted">{sel.type} · {sel.id}</p>
                {sel.status && <p className="mt-2"><StatusTag status={sel.status} /> {sel.action}</p>}
                <p className="mt-3 font-medium">Blast radius: {sel.blast_radius.count}</p>
                <ul className="mt-1 list-disc pl-5 text-muted">
                  {sel.blast_radius.ids.map((id) => <li key={id}>{g.data!.graph.nodes.find((n) => n.id === id)?.name ?? id}</li>)}
                </ul>
                {sel.role_hints.length > 0 && <p className="mt-3"><span className="font-medium">Role hints:</span> {sel.role_hints.join(", ")}</p>}
              </>
            ) : (
              <>
                <p className="font-medium">Legend</p>
                <ul className="mt-2 space-y-1">
                  {[["pending", "Awaiting review"], ["suppressed", "Skipped by agent"], ["approved", "Approved"], ["rejected", "Rejected"]].map(([s, l]) => (
                    <li key={s} className="flex items-center gap-2"><span className="inline-block h-3 w-3 rounded-sm border-2" style={{ borderColor: `rgb(${COLOR[s]})` }} />{l}</li>
                  ))}
                  <li className="flex items-center gap-2"><span className="inline-block h-3 w-3 rounded-sm border border-rule" />No recommendation</li>
                </ul>
              </>
            )}
          </aside>
        </div>
      </PageState>
    </>
  );
}
