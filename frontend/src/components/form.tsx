import { AlertTriangle, Check, Info } from "lucide-react";
import type { InputHTMLAttributes, ReactNode } from "react";
import { Icon } from "./Icon";

/** Figma "Field": label (13/medium) + 39px input. */
export function Field({ label, hint, error, children }: {
  label: string; hint?: ReactNode; error?: string | null; children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[13px] font-medium text-ink">{label}</span>
      {children}
      {error ? <span className="text-xs text-reject">{error}</span> : hint ? <span className="text-xs text-muted">{hint}</span> : null}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`h-[39px] w-full rounded-lg border border-rule bg-panel px-3 text-sm text-ink placeholder:text-muted/70 focus:border-approve focus:outline-none ${props.className ?? ""}`} />;
}

export function Select({ value, onChange, options, className = "" }: {
  value: string; onChange: (v: string) => void; options: string[]; className?: string;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className={`h-[39px] w-full rounded-lg border border-rule bg-panel px-3 text-sm text-ink focus:border-approve focus:outline-none ${className}`}>
      {options.map((o) => <option key={o}>{o}</option>)}
    </select>
  );
}

/** Figma "Chip": a selectable pill. */
export function Chip({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" aria-pressed={selected} onClick={onClick}
      className={`h-8 rounded-lg border px-3.5 text-[13px] font-medium ${selected ? "border-approve bg-approve/10 text-approve" : "border-rule bg-panel text-ink hover:border-muted"}`}>
      {children}
    </button>
  );
}

/** Figma "Toggle": 36x20 switch. */
export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)}
      className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${checked ? "bg-approve" : "bg-rule"}`}>
      <span className={`absolute top-0.5 size-4 rounded-full bg-white shadow transition-all ${checked ? "left-[18px]" : "left-0.5"}`} />
    </button>
  );
}

/** Figma "Setting": title + description, control on the right. */
export function Setting({ title, desc, children }: { title: string; desc: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-4 py-1">
      <div className="flex flex-1 flex-col gap-1">
        <p className="text-sm font-medium text-ink">{title}</p>
        <p className="text-[13px] text-muted">{desc}</p>
      </div>
      {children}
    </div>
  );
}

export function Checkbox({ checked, onChange, title, desc }: {
  checked: boolean; onChange: (v: boolean) => void; title: ReactNode; desc?: string;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5">
      <input type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className={`mt-0.5 flex size-4 shrink-0 items-center justify-center rounded border peer-focus-visible:ring-2 peer-focus-visible:ring-approve ${checked ? "border-approve bg-approve text-white" : "border-muted/60 bg-panel"}`}>
        {checked && <Check size={12} strokeWidth={3} />}
      </span>
      <span className="flex flex-col gap-0.5">
        <span className="text-sm text-ink">{title}</span>
        {desc && <span className="text-xs text-muted">{desc}</span>}
      </span>
    </label>
  );
}

const BANNER = {
  mem: { box: "bg-learned-soft/70", title: "text-learned", icon: <Icon name="sparkles" size={18} className="text-learned" /> },
  ok: { box: "bg-success/10", title: "text-success", icon: <Check size={18} className="text-success" /> },
  err: { box: "bg-reject/10", title: "text-reject", icon: <AlertTriangle size={18} className="text-reject" /> },
  info: { box: "bg-approve/10", title: "text-approve", icon: <Info size={18} className="text-approve" /> },
  warn: { box: "bg-warn-soft", title: "text-warn", icon: <Icon name="alert" size={18} className="text-warn" /> },
};

/** Figma "Banner/mem|ok|err|info". */
export function Banner({ kind, title, children, icon }: {
  kind: keyof typeof BANNER; title: ReactNode; children?: ReactNode; icon?: ReactNode;
}) {
  const b = BANNER[kind];
  return (
    <div className={`flex items-start gap-2.5 rounded-[10px] px-3.5 py-3 ${b.box}`} role={kind === "err" ? "alert" : "status"}>
      <span className="mt-px shrink-0">{icon ?? b.icon}</span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <p className={`text-sm font-semibold ${b.title}`}>{title}</p>
        {children && <div className="text-[13px] leading-[1.45] text-ink">{children}</div>}
      </div>
    </div>
  );
}

export function Logo({ dark = false }: { dark?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <span className="flex size-7 items-center justify-center rounded-lg bg-approve text-white"><Icon name="cloud" /></span>
      <span className={`text-lg font-bold ${dark ? "text-white" : "text-ink"}`}>CloudSense</span>
    </span>
  );
}


