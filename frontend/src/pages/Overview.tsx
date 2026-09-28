import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, money, ORG, post, type Metrics, type Rule } from "../api";
import { PageState, PageTitle, useLoad, Voice } from "../components/ui";

const pct = (v: number | null) => (v === null ? "no verdicts" : `${Math.round(v * 100)}%`);

export default function Overview() {
  const m = useLoad(() => api<Metrics>(`/orgs/${ORG}/metrics`));
  const rules = useLoad(() => api<Rule[]>(`/orgs/${ORG}/rules`));
  const [scanning, setScanning] = useState(false);
  const [showTable, setShowTable] = useState(false);

  const runScan = async () => {
    setScanning(true);
    try {
      await post(`/orgs/${ORG}/scans`);
      window.location.hash = "queue";
    } finally {
      setScanning(false);
    }
  };

  const series = (m.data?.series ?? []).map((s, i) => ({ ...s, label: `Scan ${i + 1}`,
    rate: s.acceptance_rate === null ? null : Math.round(s.acceptance_rate * 100) }));

  return (
    <>
      <PageTitle title="Overview">
        <button className="btn btn-approve" onClick={runScan} disabled={scanning}>
          {scanning ? "Starting scan…" : "Run a scan"}
        </button>
      </PageTitle>
      <PageState loading={m.loading} error={m.error} onRetry={m.reload}
        empty={m.data && m.data.series.length === 0 && "No scans yet. Connect an account in Settings, then run a scan."}>
        {m.data && (
          <>
            <dl className="grid gap-px overflow-hidden rounded-lg border border-rule bg-rule sm:grid-cols-3">
              {([["Waste found in the latest scan", m.data.savings.found],
                 ["Approved by engineers", m.data.savings.approved],
                 ["Executed", m.data.savings.executed]] as const).map(([label, v]) => (
                <div key={label} className="bg-panel p-5">
                  <dt className="text-sm text-muted">{label}</dt>
                  <dd className="mt-1 text-3xl font-semibold tabular-nums">{money(v)}<span className="text-base font-normal text-muted">/month</span></dd>
                </div>
              ))}
            </dl>

            <section className="mt-8 rounded-lg border border-rule bg-panel p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="font-semibold">Share of recommendations engineers approved, per scan</h2>
                <button className="text-sm text-muted underline" onClick={() => setShowTable(!showTable)}>
                  {showTable ? "Show chart" : "Show as table"}
                </button>
              </div>
              <p className="mt-1 text-sm text-muted">Rising means the agent stopped proposing things your team keeps saying no to.</p>
              {showTable ? (
                <table className="mt-4 w-full text-sm">
                  <thead className="text-left text-muted"><tr><th className="py-1">Scan</th><th>Approved</th><th>Rejected</th><th>Skipped by agent</th><th>Acceptance</th></tr></thead>
                  <tbody>{series.map((s) => (
                    <tr key={s.scan_id} className="border-t border-rule tabular-nums">
                      <td className="py-1">{s.label}</td><td>{s.approved}</td><td>{s.rejected}</td><td>{s.suppressed}</td><td>{pct(s.acceptance_rate)}</td>
                    </tr>))}</tbody>
                </table>
              ) : (
                <div className="mt-4 h-64" role="img" aria-label="Acceptance rate per scan">
                  <ResponsiveContainer>
                    <LineChart data={series} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
                      <CartesianGrid stroke="rgb(var(--rule))" vertical={false} />
                      <XAxis dataKey="label" tick={{ fill: "rgb(var(--muted))", fontSize: 12 }} axisLine={false} tickLine={false} />
                      <YAxis domain={[0, 100]} unit="%" tick={{ fill: "rgb(var(--muted))", fontSize: 12 }} axisLine={false} tickLine={false} />
                      <Tooltip
                        contentStyle={{ background: "rgb(var(--panel))", border: "1px solid rgb(var(--rule))", color: "rgb(var(--ink))", borderRadius: 6 }}
                        formatter={(v: number) => [`${v}%`, "Accepted"]}
                        cursor={{ stroke: "rgb(var(--muted))", strokeDasharray: "3 3" }} />
                      <Line type="monotone" dataKey="rate" stroke="rgb(var(--approve))" strokeWidth={2} connectNulls
                        dot={{ r: 4, strokeWidth: 2, stroke: "rgb(var(--panel))", fill: "rgb(var(--approve))" }}
                        activeDot={{ r: 6 }} isAnimationActive={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </section>
          </>
        )}
      </PageState>

      <section className="mt-8">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-semibold">What your engineers have taught it</h2>
          <a href="#rules" className="text-sm text-muted underline">All learned rules</a>
        </div>
        <PageState loading={rules.loading} error={rules.error} onRetry={rules.reload}
          empty={rules.data?.length === 0 && "Nothing learned yet. Reject a recommendation with a reason and it shows up here."}>
          <ol className="grid gap-4 md:grid-cols-2">
            {(rules.data ?? []).slice(0, 5).map((r) => (
              <li key={r.id} className="rounded-lg border border-rule bg-panel p-4">
                <Voice who={`Confirmed ${r.proof_count}×`}>{r.text}</Voice>
              </li>
            ))}
          </ol>
        </PageState>
      </section>
    </>
  );
}
