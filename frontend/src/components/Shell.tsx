import { Building2, LogOut, UserRound } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, ORG, post, type Me, type Metrics, type OrgInfo, type ScanSummary } from "../api";
import { Icon, type IconName } from "./Icon";

interface ShellData {
  org: OrgInfo | null; lastScan: ScanSummary | null; openCount: number | null; ruleCount: number | null;
  reviews: number;
}
interface ShellCtx extends ShellData {
  me: Me; refresh: () => void; scanNow: () => Promise<string | null>; scanning: boolean;
}

const Ctx = createContext<ShellCtx | null>(null);
export const useShell = () => useContext(Ctx)!;

export const NAV: { key: string; label: string; icon: IconName }[] = [
  { key: "overview", label: "Overview", icon: "dash" },
  { key: "recommendations", label: "Recommendations", icon: "inbox" },
  { key: "map", label: "Resource Map", icon: "net" },
  { key: "rules", label: "Learned Rules", icon: "shield" },
  { key: "playbook", label: "Playbook", icon: "book" },
  { key: "ask", label: "Ask", icon: "msg" },
  { key: "activity", label: "Activity", icon: "act" },
  { key: "settings", label: "Settings", icon: "sliders" },
];

export function relTime(iso: string | null | undefined): string {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

const initials = (name: string) => name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();

export function Shell({ page, me, onLogout, children }: {
  page: string; me: Me; onLogout: () => void; children: ReactNode;
}) {
  const [data, setData] = useState<ShellData>({ org: null, lastScan: null, openCount: null, ruleCount: null,
    reviews: 0 });
  const [scanning, setScanning] = useState(false);

  const refresh = useCallback(async () => {
    const [org, scans, rules, metrics] = await Promise.all([
      api<OrgInfo>(`/orgs/${ORG}`).catch(() => null),
      api<ScanSummary[]>(`/orgs/${ORG}/scans`).catch(() => [] as ScanSummary[]),
      api<unknown[]>(`/orgs/${ORG}/rules`).catch(() => null),
      api<Metrics>(`/orgs/${ORG}/metrics`).catch(() => null),
    ]);
    let openCount: number | null = null;
    const last = scans[0] ?? null;
    if (last?.status === "done") {
      const d = await api<{ recommended: unknown[]; asked: unknown[] }>(`/orgs/${ORG}/scans/${last.id}`).catch(() => null);
      openCount = d ? d.recommended.length + d.asked.length : null;
    }
    const reviews = (metrics?.series ?? []).reduce((n, s) => n + s.approved + s.rejected, 0);
    setData({ org, lastScan: last, openCount, ruleCount: rules ? rules.length : null, reviews });
  }, []);

  useEffect(() => { refresh(); }, [refresh, page]);

  const scanNow = async (): Promise<string | null> => {
    setScanning(true);
    try {
      const r = await post<{ scan_id: string }>(`/orgs/${ORG}/scans`);
      await refresh();
      return r.scan_id;
    } catch {
      return null;
    } finally {
      setScanning(false);
    }
  };

  const badge = (key: string) => (key === "recommendations" ? data.openCount : key === "rules" ? data.ruleCount : null);

  return (
    <Ctx.Provider value={{ ...data, me, refresh, scanNow, scanning }}>
      <div className="flex min-h-screen bg-paper">
        <aside className="sticky top-0 flex h-screen w-[248px] shrink-0 flex-col gap-1 bg-side-bg px-3.5 py-5">
          <a href="#overview" className="flex items-center gap-2.5 px-2 pb-3 pt-1">
            <span className="flex size-7 items-center justify-center rounded-lg bg-approve text-white">
              <Icon name="cloud" />
            </span>
            <span className="text-[17px] font-bold text-white">CloudSense</span>
          </a>
          <div className="flex items-center gap-2 rounded-lg bg-side-raised px-2.5 py-2">
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <p className="truncate text-[13px] font-semibold text-white">{data.org?.name ?? me.org.name}</p>
              <p className="text-[11px] text-side-text">
                {data.org ? `${data.org.accounts.length} AWS account${data.org.accounts.length === 1 ? "" : "s"}` : " "}
              </p>
            </div>
            <Icon name="chev" size={14} className="text-side-text" />
          </div>
          <div className="h-3" />
          <nav aria-label="Pages" className="flex flex-col gap-1">
            {NAV.map((n) => {
              const active = page === n.key;
              const count = badge(n.key);
              return (
                <a key={n.key} href={`#${n.key}`} aria-current={active ? "page" : undefined}
                  className={`flex items-center gap-2.5 rounded-lg px-2.5 py-[9px] ${active ? "bg-side-raised" : "hover:bg-side-raised/60"}`}>
                  <Icon name={n.icon} className={active ? "text-side-active" : "text-side-text"} />
                  <span className={`flex-1 text-sm font-medium ${active ? "text-white" : "text-side-text"}`}>{n.label}</span>
                  {count ? <span className="rounded-full bg-side-raised px-[7px] py-px text-[11px] font-semibold text-side-soft">{count}</span> : null}
                </a>
              );
            })}
          </nav>
          <div className="flex-1" />
          <div className="flex flex-col gap-1.5 rounded-[10px] bg-side-raised p-3">
            <div className="flex items-center gap-1.5">
              <Icon name="sparkles" size={14} className="text-side-memory" />
              <p className="text-xs font-semibold text-side-memory">Memory</p>
            </div>
            <p className="text-xs text-side-soft">
              {data.ruleCount ?? 0} rule{data.ruleCount === 1 ? "" : "s"} learned from {data.reviews} review{data.reviews === 1 ? "" : "s"}
            </p>
          </div>
          <UserMenu me={me} onLogout={onLogout} />
        </aside>
        <main className="flex min-w-0 flex-1 flex-col gap-5 px-8 pb-8 pt-7">{children}</main>
      </div>
    </Ctx.Provider>
  );
}

function UserMenu({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);
  const item = "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-[13px] text-ink hover:bg-paper";
  return (
    <div ref={ref} className="relative">
      {open && (
        <div role="menu" className="absolute bottom-full left-0 right-0 mb-2 rounded-lg border border-rule bg-panel p-1.5 shadow-lg">
          <p className="truncate px-2.5 pb-1.5 pt-1 text-xs text-muted">{me.user.email}</p>
          <a role="menuitem" href="#profile" className={item} onClick={() => setOpen(false)}>
            <UserRound size={15} strokeWidth={1.75} /> Profile
          </a>
          <a role="menuitem" href="#settings" className={item} onClick={() => setOpen(false)}>
            <Building2 size={15} strokeWidth={1.75} /> Company details
          </a>
          <div className="my-1 h-px bg-rule" />
          <button role="menuitem" className={`${item} text-reject`} onClick={onLogout}>
            <LogOut size={15} strokeWidth={1.75} /> Log out
          </button>
        </div>
      )}
      <button aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2.5 text-left hover:bg-side-raised/60">
        <span className="flex size-[30px] shrink-0 items-center justify-center rounded-full bg-side-avatar text-[11px] font-semibold text-white">
          {initials(me.user.name)}
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-px">
          <span className="truncate text-[13px] font-semibold text-white">{me.user.name}</span>
          <span className="text-[11px] capitalize text-side-text">{me.user.role}</span>
        </span>
        <Icon name="chev" size={14} className={`text-side-text transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
    </div>
  );
}

/** Figma "Top bar": title + subtitle, then DRY RUN pill · last scan · Scan now · bell. */
export function TopBar({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children?: ReactNode }) {
  const { org, lastScan, scanNow, scanning } = useShell();
  return (
    <header className="flex flex-wrap items-center gap-4">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-[-0.24px] text-ink">{title}</h1>
        {subtitle && <p className="text-sm text-muted">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-3">
        {children}
        {org?.dry_run && (
          <span className="flex items-center gap-1 rounded-full bg-warn-soft px-[9px] py-[3px] text-xs font-medium text-warn"
            title="Approved actions only show the AWS calls they would make">
            <Icon name="eye" size={12} /> DRY RUN
          </span>
        )}
        <span className="text-[13px] text-muted">
          {lastScan?.status === "running" ? "Scanning…" : `Last scan ${relTime(lastScan?.started_at)}`}
        </span>
        <button className="btn" disabled={scanning || lastScan?.status === "running"}
          onClick={async () => { const id = await scanNow(); if (id) window.location.hash = `scan/${id}`; }}>
          {scanning ? "Starting…" : "Scan now"}
        </button>
        <a href="#activity" aria-label="Activity" className="rounded-lg border border-rule bg-panel p-2 text-ink hover:border-muted">
          <Icon name="bell" />
        </a>
      </div>
    </header>
  );
}
