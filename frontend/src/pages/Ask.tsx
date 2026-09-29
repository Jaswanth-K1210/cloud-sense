import { ExternalLink, UserRound } from "lucide-react";
import Markdown from "react-markdown";
import { useState } from "react";
import { ORG, post, type MemoryHit } from "../api";
import { Icon } from "../components/Icon";
import { Banner } from "../components/form";
import { Pill, quoteParts } from "../components/bits";
import { TopBar, useShell } from "../components/Shell";

const SUGGESTED = ["What should we never touch in prod?", "Can we stop standby databases?", "What did the Payments team reject this month?"];
const FOLLOW_UPS = ["When is it safe to rightsize?", "Which resources are protected by learned rules?"];
const HISTORY_KEY = "cloudsense.askHistory";

function loadHistory(): string[] {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]"); } catch { return []; }
}
function saveHistory(h: string[]): void {
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(h.slice(0, 8))); } catch { /* per-browser convenience only */ }
}

function Source({ hit }: { hit: MemoryHit }) {
  const q = quoteParts(hit.text);
  const rejected = hit.text.includes("Verdict: REJECT");
  const title = q.who && q.proposal ? `${q.who} ${rejected ? "rejected" : "approved"}: ${q.proposal}`
    : hit.type === "mental_model" ? "Team playbook" : hit.text.split("\n")[0].slice(0, 90);
  const sub = q.reason ? `“${q.reason}”${q.when ? ` · ${q.when}` : ""}` : hit.type === "mental_model" ? "Auto-written from your team’s decisions" : hit.text.slice(90, 180);
  return (
    <li className="flex items-start gap-3 py-2.5">
      <span className="mt-0.5 text-muted">{hit.type === "mental_model" ? <Icon name="book" size={14} /> : <UserRound size={14} />}</span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <p className="text-sm text-ink">{title}</p>
        {sub && <p className="text-xs text-muted">{sub}</p>}
      </div>
      <a href={hit.type === "mental_model" ? "#playbook" : "#rules"} aria-label="Open" className="text-muted hover:text-approve"><ExternalLink size={14} /></a>
    </li>
  );
}

/** Figma 19: answers cite past decisions. */
export default function Ask() {
  const { me } = useShell();
  const [q, setQ] = useState("");
  const [asked, setAsked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<{ text: string; based_on: MemoryHit[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>(loadHistory);
  const initials = me.user.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();

  const ask = async (question: string) => {
    if (!question.trim()) return;
    setBusy(true); setError(null); setAsked(question); setAnswer(null); setQ("");
    const h = [question, ...history.filter((x) => x !== question)];
    setHistory(h); saveHistory(h);
    try {
      setAnswer(await post(`/orgs/${ORG}/ask`, { question }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <TopBar title="Ask" subtitle="Questions about your cloud rules and past decisions. Every answer cites its sources." />
      <div className="flex flex-wrap items-start gap-5">
        <aside className="card flex w-full flex-col gap-2 p-5 lg:w-[250px]">
          <p className="text-[13px] font-semibold text-ink">Recent questions</p>
          {history.length === 0 && <p className="text-[13px] text-muted">Your questions will appear here.</p>}
          {history.map((h) => (
            <button key={h} onClick={() => ask(h)} className="rounded-lg px-2 py-1.5 text-left text-[13px] text-ink hover:bg-paper">{h}</button>
          ))}
        </aside>
        <div className="flex min-w-[340px] flex-1 flex-col gap-4">
          <form className="card flex items-center gap-3 px-4 py-3" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
            <Icon name="sparkles" size={18} className="text-learned" />
            <input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Ask a question"
              placeholder="Ask about your cloud rules and past decisions…" className="h-9 flex-1 bg-transparent text-[15px] outline-none" />
            <button className="btn btn-approve h-[35px]" disabled={busy || !q.trim()}>{busy ? "…" : "Ask"}</button>
          </form>
          <div className="flex flex-wrap gap-2">
            {SUGGESTED.map((s) => <button key={s} onClick={() => ask(s)} className="h-8 rounded-lg border border-rule bg-panel px-3.5 text-[13px] font-medium text-ink hover:border-muted">{s}</button>)}
          </div>
          {asked && (
            <div className="flex items-start justify-end gap-2">
              <p className="rounded-xl bg-approve/10 px-4 py-2.5 text-[15px] text-ink">{asked}</p>
              <span className="flex size-7 items-center justify-center rounded-full bg-side-avatar text-[11px] font-semibold text-white">{initials}</span>
            </div>
          )}
          {error && <Banner kind="err" title={`Couldn’t get an answer: ${error}`} />}
          {busy && <p className="card p-6 text-sm text-muted" role="status">Thinking through your team’s decisions…</p>}
          {answer && (
            <section className="card flex flex-col gap-4 p-6" aria-live="polite">
              <div className="flex items-center gap-2">
                <Icon name="sparkles" size={16} className="text-learned" />
                <span className="flex-1 text-sm font-semibold text-ink">CloudSense</span>
                <Pill tone="learned">Based on {answer.based_on.length} source{answer.based_on.length === 1 ? "" : "s"}</Pill>
              </div>
              <div className="space-y-3 text-[15px] leading-[1.55] text-ink [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:text-base [&_h2]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_strong]:font-semibold">
                <Markdown>{answer.text}</Markdown>
              </div>
              {answer.based_on.length > 0 && (
                <>
                  <div className="h-px bg-rule" />
                  <p className="text-[11px] font-semibold tracking-[0.8px] text-muted">SOURCES</p>
                  <ul className="divide-y divide-rule">{answer.based_on.map((h) => <Source key={h.id} hit={h} />)}</ul>
                </>
              )}
              <div className="flex flex-wrap gap-2">
                {FOLLOW_UPS.map((s) => <button key={s} onClick={() => ask(s)} className="h-8 rounded-lg border border-rule bg-panel px-3.5 text-[13px] font-medium text-ink hover:border-muted">{s}</button>)}
              </div>
            </section>
          )}
        </div>
      </div>
    </>
  );
}
