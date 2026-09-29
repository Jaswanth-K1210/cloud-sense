import { useState } from "react";
import { api, memoryParts, ORG, type Rule } from "../api";
import { PageState, PageTitle, useLoad, Voice } from "../components/ui";

export default function Rules() {
  const rules = useLoad(() => api<Rule[]>(`/orgs/${ORG}/rules`));
  const [confirming, setConfirming] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const remove = async (id: string) => {
    try {
      await api(`/orgs/${ORG}/rules/${id}`, { method: "DELETE" });
      setConfirming(null);
      rules.reload();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <>
      <PageTitle title="Learned Rules" />
      <p className="-mt-4 mb-6 max-w-2xl text-sm text-muted">
        Each rule is consolidated from engineers' verdicts. The agent applies them to look-alike resources, even untagged ones.
        Hard rules you write in Settings always win.
      </p>
      {error && <p className="mb-4 text-sm text-reject" role="alert">{error}</p>}
      <PageState loading={rules.loading} error={rules.error} onRetry={rules.reload}
        empty={rules.data?.length === 0 && "No rules yet. Reject a recommendation in the Queue with a reason, and CloudSense learns from it."}>
        <ul className="space-y-4">
          {(rules.data ?? []).map((r) => (
            <li key={r.id} className="rounded-lg border border-rule bg-panel p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="max-w-3xl"><Voice>{r.text}</Voice></div>
                <p className="shrink-0 text-sm font-semibold text-learned">Confirmed {r.proof_count}×</p>
              </div>
              {r.tags.length > 0 && <p className="mt-2 text-xs text-muted">Scope: {r.tags.join(", ")}</p>}
              <details className="mt-3 text-sm">
                <summary className="cursor-pointer text-muted">Where it came from ({r.sources.length})</summary>
                <ul className="mt-2 space-y-2">
                  {r.sources.map((s) => {
                    const p = memoryParts(s.text);
                    const who = s.text.match(/^Reviewer (.+?) at (\S+?):/m);
                    return (
                      <li key={s.id} className="border-l-2 border-rule pl-3">
                        {who && <p className="text-xs text-muted">{who[1]}, {new Date(who[2]).toLocaleString()}</p>}
                        {p.proposal && <p>Proposed: {p.proposal}</p>}
                        {p.reason ? <p className="font-voice italic">“{p.reason}”</p> : <p>{s.text || s.id}</p>}
                      </li>
                    );
                  })}
                </ul>
              </details>
              <div className="mt-3">
                {confirming === r.id ? (
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span>Delete this rule? The agent stops applying it on the next scan.</span>
                    <button className="btn btn-reject" onClick={() => remove(r.id)}>Delete rule</button>
                    <button className="btn" onClick={() => setConfirming(null)}>Keep it</button>
                  </div>
                ) : (
                  <button className="text-sm text-muted underline" onClick={() => setConfirming(r.id)}>Delete (admins)</button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </PageState>
    </>
  );
}
