import { diffLines } from "diff";
import { Copy, Link2, Printer } from "lucide-react";
import { useState } from "react";
import Markdown from "react-markdown";
import { api, ORG, type OrgInfo } from "../api";
import { Icon } from "../components/Icon";
import { Pill } from "../components/bits";
import { TopBar } from "../components/Shell";
import { PageState, useLoad } from "../components/ui";

interface PlaybookResp {
  current: { content: string; last_refreshed_at: string | null;
    structured: { protected_patterns?: { pattern: string; reason?: string; applies_to?: string }[]; safe_patterns?: string[] } | null };
  history: { content: string; changed_at: string | null }[];
}

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString([], { month: "short", day: "numeric" }) : "");

function summary(before: string, after: string): string {
  const added = diffLines(before, after).filter((p) => p.added).map((p) => p.value.trim()).join(" ").replace(/[#*-]+/g, "").trim();
  const removed = diffLines(before, after).some((p) => p.removed);
  if (!before.trim()) return "Created";
  return added ? `${removed ? "Updated" : "Added"}: ${added.slice(0, 60)}${added.length > 60 ? "…" : ""}` : "Wording changes";
}

/** Figma 18: auto-written, versioned playbook. */
export default function Playbook() {
  const pb = useLoad(() => api<PlaybookResp>(`/orgs/${ORG}/playbook`));
  const org = useLoad(() => api<OrgInfo>(`/orgs/${ORG}`));
  const [picked, setPicked] = useState(0);
  const [copied, setCopied] = useState<string | null>(null);
  const d = pb.data;
  const versions = d ? [{ content: d.current.content, changed_at: d.current.last_refreshed_at }, ...d.history] : [];
  const vNum = (i: number) => versions.length - i; // newest = highest
  const before = (i: number) => versions[i + 1]?.content ?? "";
  const s = d?.current.structured;
  const copy = (text: string, what: string) => navigator.clipboard?.writeText(text).then(() => { setCopied(what); setTimeout(() => setCopied(null), 1500); });

  return (
    <>
      <TopBar title={`${org.data?.name ?? "Team"} Cost Playbook`}
        subtitle={`Auto-written from your team’s decisions${d?.current.last_refreshed_at ? ` · Updated ${when(d.current.last_refreshed_at)}` : ""}`} />
      <PageState loading={pb.loading && !d} error={pb.error} onRetry={pb.reload}
        empty={d && !d.current.content && !s?.protected_patterns?.length && "The playbook is empty. It writes itself after your team reviews a few recommendations."}>
        {d && (
          <div className="flex flex-wrap items-start gap-5">
            <article className="card flex min-w-[340px] flex-1 flex-col gap-6 p-7 print:border-0">
              <div className="flex flex-wrap items-center gap-2 print:hidden">
                <Pill tone="approve">v{versions.length} · current</Pill>
                <span className="flex-1" />
                <button className="btn h-[31px]" onClick={() => window.print()}><Printer size={14} /> Export PDF</button>
                <button className="btn h-[31px]" onClick={() => copy(d.current.content, "md")}><Copy size={14} /> {copied === "md" ? "Copied" : "Copy as Markdown"}</button>
                <button className="btn h-[31px]" onClick={() => copy(window.location.href, "link")}><Link2 size={14} /> {copied === "link" ? "Copied" : "Share link"}</button>
              </div>
              {s?.protected_patterns?.length ? (
                <>
                  <PlaySection title="Never touch" items={s.protected_patterns.map((p) => ({ text: `${p.pattern}${p.reason && p.reason !== p.pattern ? `. ${p.reason}` : ""}`,
                    pill: !p.applies_to || ["org", "all", "all accounts"].includes(p.applies_to.toLowerCase()) ? "All accounts" : p.applies_to }))} />
                  {!!s.safe_patterns?.length && <PlaySection title="Safe to optimize" items={s.safe_patterns.map((t) => ({ text: t }))} />}
                </>
              ) : (
                <div className="max-w-[70ch] space-y-3 text-[15px] leading-[1.55] text-ink [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:mt-5 [&_h2]:text-lg [&_h2]:font-semibold [&_li]:ml-5 [&_li]:list-disc">
                  <Markdown>{d.current.content}</Markdown>
                </div>
              )}
              {!!org.data?.hard_rules.length && (
                <PlaySection title="Team notes" items={org.data.hard_rules.map((h) => ({ text: h, pill: "Hard rule" }))} />
              )}
            </article>
            <aside className="card flex w-full flex-col gap-4 p-5 lg:w-[340px] print:hidden">
              <h2 className="text-[15px] font-semibold text-ink">Version history</h2>
              <ol className="flex flex-col gap-1">
                {versions.map((v, i) => (
                  <li key={i}>
                    <button onClick={() => setPicked(i)} className={`flex w-full items-start gap-3 rounded-lg px-2.5 py-2 text-left ${picked === i ? "bg-paper" : "hover:bg-paper/60"}`}>
                      <span className="w-6 text-sm font-semibold text-ink">v{vNum(i)}</span>
                      <span className="flex-1 text-[13px] text-ink">{summary(before(i), v.content)}</span>
                      <span className="text-xs text-muted">{when(v.changed_at)}</span>
                    </button>
                  </li>
                ))}
              </ol>
              {versions.length > 0 && (
                <>
                  <p className="text-[13px] font-semibold text-ink">Changes in v{vNum(picked)}</p>
                  <div className="overflow-x-auto rounded-lg bg-paper p-3 font-mono text-xs leading-5" aria-label="What changed">
                    {diffLines(before(picked), versions[picked].content).map((part, i) => (
                      <pre key={i} className={`whitespace-pre-wrap ${part.added ? "text-success" : part.removed ? "text-reject line-through" : "text-muted"}`}>
                        {part.value.split("\n").filter(Boolean).map((l) => `${part.added ? "+ " : part.removed ? "- " : "  "}${l}`).join("\n")}
                      </pre>
                    ))}
                  </div>
                </>
              )}
            </aside>
          </div>
        )}
      </PageState>
    </>
  );
}

function PlaySection({ title, items }: { title: string; items: { text: string; pill?: string | null }[] }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
      <ul className="flex flex-col gap-3">
        {items.map((it, i) => (
          <li key={i} className="flex items-start gap-3">
            <span className="mt-2 size-1.5 shrink-0 rounded-full bg-ink" />
            <span className="flex flex-1 flex-wrap items-center gap-2 text-[15px] leading-[1.5] text-ink">
              {it.text}
              {it.pill && <Pill tone="learned" icon={<Icon name="sparkles" size={12} />}>{it.pill}</Pill>}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
