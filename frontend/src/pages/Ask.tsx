import { useState } from "react";
import { ORG, post, type MemoryHit } from "../api";
import { MemoryList, PageTitle } from "../components/ui";

const EXAMPLES = ["Can we downsize the payroll workers?", "What did the payments team tell us not to touch?",
  "Which standbys are safe to stop?"];

export default function Ask() {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<{ text: string; based_on: MemoryHit[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ask = async (question: string) => {
    if (!question.trim()) return;
    setBusy(true);
    setError(null);
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
      <PageTitle title="Ask" />
      <form className="max-w-2xl" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
        <label htmlFor="q" className="text-sm font-medium">Ask about your team's past decisions</label>
        <div className="mt-1 flex gap-2">
          <input id="q" className="field" value={q} onChange={(e) => setQ(e.target.value)} placeholder={EXAMPLES[0]} />
          <button className="btn btn-approve shrink-0" disabled={busy || !q.trim()}>{busy ? "Thinking…" : "Ask"}</button>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button key={ex} type="button" className="text-sm text-muted underline" onClick={() => { setQ(ex); ask(ex); }}>{ex}</button>
          ))}
        </div>
      </form>
      {error && <p className="mt-6 text-sm text-reject" role="alert">Couldn't get an answer: {error}</p>}
      {answer && (
        <section className="mt-8 max-w-3xl rounded-lg border border-rule bg-panel p-5" aria-live="polite">
          <p className="whitespace-pre-wrap">{answer.text}</p>
          <h2 className="mb-2 mt-5 text-sm font-semibold">Based on</h2>
          <MemoryList hits={answer.based_on} />
        </section>
      )}
    </>
  );
}
