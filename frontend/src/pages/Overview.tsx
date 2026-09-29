import { api, money, ORG, type Candidate, type Metrics, type Rule, type ScanDetail } from "../api";
import { Icon } from "../components/Icon";
import { relTime, TopBar, useShell } from "../components/Shell";
import { useLoad } from "../components/ui";

const SERVICE: Record<string, string> = { ec2: "EC2", ebs: "EBS", rds: "RDS", s3: "S3", eip: "Elastic IPs",
  snapshot: "Snapshots" };
const BAR_PX_PER_100 = 180; // Figma: 91% -> 164px
const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);

interface Data { metrics: Metrics; rules: Rule[]; scan: ScanDetail | null }

async function load(): Promise<Data> {
  const [metrics, rules, scans] = await Promise.all([
    api<Metrics>(`/orgs/${ORG}/metrics`), api<Rule[]>(`/orgs/${ORG}/rules`),
    api<{ id: string; status: string }[]>(`/orgs/${ORG}/scans`),
  ]);
  const done = scans.find((s) => s.status === "done");
  const scan = done ? await api<ScanDetail>(`/orgs/${ORG}/scans/${done.id}`) : null;
  return { metrics, rules, scan };
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** Figma: "today 9:42 AM"; older scans show the weekday or date. */
function scanTime(iso: string): string {
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const days = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 864e5);
  if (days === 0) return `today ${time}`;
  if (days === 1) return `yesterday ${time}`;
  return `${d.toLocaleDateString([], days < 7 ? { weekday: "long" } : { month: "short", day: "numeric" })} ${time}`;
}

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

function Kpi({ label, value, unit, note, noteClass = "text-approve", violet = false }: {
  label: string; value: string; unit?: string; note: string; noteClass?: string; violet?: boolean;
}) {
  return (
    <div className={`flex min-w-[180px] flex-1 flex-col gap-1.5 rounded-xl border p-5 ${violet ? "border-learned-line bg-learned-card" : "border-rule bg-panel"}`}>
      <p className="text-[13px] font-medium text-muted">{label}</p>
      <p className="flex items-baseline gap-1">
        <span className={`text-[30px] font-bold tracking-[-0.3px] ${violet ? "text-learned" : "text-ink"}`}>{value}</span>
        {unit && <span className="text-sm text-muted">{unit}</span>}
      </p>
      <p className={`text-xs font-medium ${violet ? "text-learned" : noteClass}`}>{note}</p>
    </div>
  );
}

function RuleChip() {
  return (
    <span className="flex items-center gap-[3px] rounded-full bg-learned-soft px-1.5 py-0.5 text-[10px] font-semibold text-learned">
      <Icon name="sparkles" size={10} /> rule
    </span>
  );
}

function AcceptanceChart({ series }: { series: Metrics["series"] }) {
  const last10 = series.slice(-10);
  return (
    <section className="card flex min-w-0 flex-1 flex-col gap-4 p-6" aria-label="Acceptance rate per scan">
      <div className="flex items-center">
        <div className="flex flex-1 flex-col gap-0.5">
          <h2 className="text-base font-semibold text-ink">Acceptance rate per scan</h2>
          <p className="text-[13px] text-muted">Higher = CloudSense understands your team better</p>
        </div>
        <span className="flex items-center gap-1.5 rounded-lg border border-rule bg-panel px-2.5 py-[7px] text-[13px] font-medium text-ink">
          Last 10 scans <Icon name="chev" size={14} className="text-muted" />
        </span>
      </div>
      {last10.length === 0 ? (
        <p className="flex h-[250px] items-center justify-center text-sm text-muted">
          No scans yet. Run a scan, then approve or reject what it finds.
        </p>
      ) : (
        <div className="flex h-[250px] items-end justify-between gap-2">
          {last10.map((s, i) => {
            const latest = i === last10.length - 1;
            const rate = s.acceptance_rate;
            return (
              <div key={s.scan_id} className="flex flex-col items-center gap-1.5"
                title={`Scan ${series.length - last10.length + i + 1}: ${s.approved} approved, ${s.rejected} rejected, ${s.suppressed} skipped`}>
                {s.rules_learned > 0 && <RuleChip />}
                <span className={`text-[11px] font-semibold ${latest ? "text-approve" : "text-muted"}`}>{pct(rate)}</span>
                <span className={`w-7 rounded-t-md ${latest ? "bg-approve" : "bg-approve-soft"}`}
                  style={{ height: Math.max(4, (rate ?? 0) * BAR_PX_PER_100) }} />
                <span className="text-[11px] text-muted">S{series.length - last10.length + i + 1}</span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function recentLearning(rules: Rule[]) {
  return [...rules]
    .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""))
    .slice(0, 3)
    .map((r) => {
      const who = r.sources.map((s) => s.text.match(/Reviewer (.+?) \(/)?.[1]).find(Boolean);
      return { id: r.id, text: r.text, count: r.proof_count, meta: [who, r.updated_at ? relTime(r.updated_at) : null].filter(Boolean).join(" · ") };
    });
}

function grouped(cands: Candidate[], key: (c: Candidate) => string) {
  const m = new Map<string, { total: number; open: number }>();
  for (const c of cands) {
    const g = m.get(key(c)) ?? { total: 0, open: 0 };
    g.total += c.monthly_saving ?? 0;
    g.open += 1;
    m.set(key(c), g);
  }
  return [...m.entries()].sort((a, b) => b[1].total - a[1].total);
}

export default function Overview() {
  const shell = useShell();
  const { data, error, loading, reload } = useLoad(load, [shell.lastScan?.id, shell.lastScan?.status]);

  if (loading && !data) return <><TopBar title="Overview" /><p className="py-10 text-muted" role="status">Loading…</p></>;
  if (error || !data)
    return (
      <><TopBar title="Overview" />
        <div className="card p-5" role="alert">
          <p className="font-semibold text-reject">Couldn't load the overview: {error}</p>
          <button className="btn mt-3" onClick={reload}>Try again</button>
        </div></>
    );

  const { metrics, rules, scan } = data;
  const me = shell.me.user;
  const s = metrics.series;
  const latest = s.at(-1);
  const prev = s.at(-2);
  const firstRate = s.find((x) => x.acceptance_rate !== null)?.acceptance_rate;
  const delta = prev ? metrics.savings.found - prev.found : null;
  const rulesThisWeek = rules.filter((r) => r.updated_at && Date.now() - new Date(r.updated_at).getTime() < 7 * 864e5).length;
  const open = scan ? [...scan.recommended, ...scan.asked] : [];
  const byService = grouped(open, (c) => SERVICE[c.resource.type] ?? c.resource.type);
  const byAccount = grouped(open, (c) => c.resource.account ?? "unknown");
  const maxService = Math.max(1, ...byService.map(([, g]) => g.total));
  const firstName = me?.name.split(" ")[0];

  return (
    <>
      <TopBar title="Overview"
        subtitle={`${greeting()}${firstName ? `, ${firstName}` : ""}. ${rulesThisWeek
          ? `CloudSense learned ${rulesThisWeek} new rule${rulesThisWeek === 1 ? "" : "s"} this week.`
          : rules.length ? `CloudSense knows ${rules.length} rule${rules.length === 1 ? "" : "s"} from your team.`
            : "Reject a recommendation with a reason and CloudSense learns from it."}`} />

      <div className="flex flex-wrap gap-5">
        <Kpi label="Potential savings" value={money(metrics.savings.found)} unit="/mo"
          note={delta === null ? `${open.length} open recommendation${open.length === 1 ? "" : "s"}`
            : `${delta >= 0 ? "+" : "−"}${money(Math.abs(delta))} vs last scan`} />
        <Kpi label="Approved savings" value={money(metrics.savings.approved)} unit="/mo"
          note={`${metrics.savings.approved_count} recommendation${metrics.savings.approved_count === 1 ? "" : "s"}`} />
        <Kpi label="Realized savings" value={money(metrics.savings.executed)} unit="/mo" noteClass="text-success"
          note={metrics.savings.executed_count ? "Executed, undo available" : "Nothing executed yet"} />
        <Kpi violet label="Acceptance rate" value={pct(latest?.acceptance_rate)}
          note={latest?.acceptance_rate != null && firstRate != null && s.length > 1
            ? `${latest.acceptance_rate >= firstRate ? "+" : "−"}${Math.round(Math.abs(latest.acceptance_rate - firstRate) * 100)} pts since scan 1`
            : "Approved ÷ (approved + rejected)"} />
      </div>

      <div className="flex flex-wrap items-start gap-5">
        <AcceptanceChart series={s} />
        <div className="flex w-full flex-col gap-5 lg:w-[380px]">
          <section className="card flex flex-col gap-3 p-5">
            <div className="flex items-center">
              <h2 className="text-[15px] font-semibold text-ink">Recent learning</h2>
              <span className="flex-1" />
              <a href="#rules" className="text-sm font-semibold text-approve hover:underline">All rules</a>
            </div>
            {rules.length === 0 && <p className="text-[13px] text-muted">Nothing learned yet. Rejections with a reason show up here.</p>}
            {recentLearning(rules).map((r) => (
              <div key={r.id} className="flex items-start gap-2.5">
                <span className="flex size-[26px] shrink-0 items-center justify-center rounded-full bg-learned-soft text-learned">
                  <Icon name="sparkles" size={13} />
                </span>
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <p className="text-sm font-medium text-ink">{r.text}{r.count > 1 ? ` (${r.count}×)` : ""}</p>
                  {r.meta && <p className="text-xs text-muted">{r.meta}</p>}
                </div>
              </div>
            ))}
          </section>

          {scan && scan.asked.length > 0 && (
            <a href="#recommendations" className="flex items-start gap-2.5 rounded-[10px] bg-warn-soft px-3.5 py-3 text-warn">
              <Icon name="alert" size={18} />
              <div className="flex flex-1 flex-col gap-0.5">
                <p className="text-sm font-semibold">
                  {scan.asked.length} recommendation{scan.asked.length === 1 ? " needs" : "s need"} your input
                </p>
                <p className="text-[13px] leading-[1.45] text-ink">
                  CloudSense isn’t sure about {scan.asked.slice(0, 2).map((c) => c.resource.name).join(" and ")}
                  {scan.asked.length > 2 ? ` and ${scan.asked.length - 2} more` : ""}.
                </p>
              </div>
            </a>
          )}

          <section className="card flex flex-col gap-2.5 p-5">
            <h2 className="text-sm font-semibold text-ink">
              Last scan: {scan ? scanTime(scan.started_at) : "none yet"}
            </h2>
            <p className="text-[13px] text-muted">
              {scan ? `${scan.resource_count} resources · ${plural(open.length, "recommendation")} · ${scan.suppressed.length} skipped`
                : "Connect an account in Settings, then run a scan."}
            </p>
          </section>
        </div>
      </div>

      <div className="flex flex-wrap items-start gap-5">
        <section className="card flex min-w-0 flex-1 flex-col gap-3 p-6">
          <h2 className="text-[15px] font-semibold text-ink">Potential savings by service</h2>
          {byService.length === 0 && <p className="text-[13px] text-muted">No open recommendations.</p>}
          {byService.map(([name, g]) => (
            <div key={name} className="flex items-center gap-3">
              <span className="w-[90px] text-[13px] text-muted">{name}</span>
              <span className="h-2.5 flex-1 overflow-hidden rounded-[5px] bg-track">
                <span className="block h-full rounded-[5px] bg-approve" style={{ width: `${(g.total / maxService) * 100}%` }} />
              </span>
              <span className="w-[70px] text-right text-[13px] font-semibold text-ink">{money(g.total)}</span>
            </div>
          ))}
        </section>
        <section className="card flex w-full flex-col gap-3 p-6 lg:w-[380px]">
          <h2 className="text-[15px] font-semibold text-ink">By account</h2>
          {byAccount.length === 0 && <p className="text-[13px] text-muted">No open recommendations.</p>}
          {byAccount.map(([name, g]) => (
            <div key={name} className="flex items-center gap-2.5">
              <span className="text-sm font-medium text-ink">{name}</span>
              <span className="flex-1" />
              <span className="text-xs text-muted">{g.open} open</span>
              <span className="text-sm font-semibold text-ink">{money(g.total)}/mo</span>
            </div>
          ))}
        </section>
      </div>
    </>
  );
}
