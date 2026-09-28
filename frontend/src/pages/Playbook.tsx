import { useState } from "react";
import Markdown from "react-markdown";
import { diffLines } from "diff";
import { api, ORG } from "../api";
import { PageState, PageTitle, useLoad } from "../components/ui";

interface PlaybookResp {
  current: { content: string; last_refreshed_at: string | null;
    structured: { protected_patterns?: { pattern: string; reason: string }[] } | null };
  history: { content: string; changed_at: string | null }[];
}

export default function Playbook() {
  const pb = useLoad(() => api<PlaybookResp>(`/orgs/${ORG}/playbook`));
  const [picked, setPicked] = useState(0);
  const d = pb.data;
  // history[i] is the content before change i (most recent first); compare it to the version after it.
  const after = (i: number) => (i === 0 ? d!.current.content : d!.history[i - 1].content);

  return (
    <>
      <PageTitle title="Playbook" />
      <p className="-mt-4 mb-6 max-w-2xl text-sm text-muted">
        The living "what we never touch and why" document. CloudSense rewrites it after each round of learning.
      </p>
      <PageState loading={pb.loading} error={pb.error} onRetry={pb.reload}
        empty={d && !d.current.content && "The playbook is empty. It fills in after engineers review a few recommendations."}>
        {d && (
          <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
            <article className="rounded-lg border border-rule bg-panel p-6">
              {d.current.last_refreshed_at && <p className="mb-3 text-xs text-muted">Updated {new Date(d.current.last_refreshed_at).toLocaleString()}</p>}
              {(d.current.structured?.protected_patterns?.length ?? 0) > 0 && (
                <ul className="mb-5 flex flex-wrap gap-2">
                  {d.current.structured!.protected_patterns!.map((p) => (
                    <li key={p.pattern} title={p.reason} className="rounded border border-learned/50 px-2 py-0.5 text-xs text-learned">{p.pattern.slice(0, 60)}</li>
                  ))}
                </ul>
              )}
              <div className="prose-sm max-w-[70ch] space-y-3 [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:font-semibold [&_li]:ml-5 [&_li]:list-disc">
                <Markdown>{d.current.content}</Markdown>
              </div>
            </article>
            <aside>
              <h2 className="mb-2 font-semibold">History</h2>
              {d.history.length === 0 ? <p className="text-sm text-muted">No earlier versions yet.</p> : (
                <>
                  <ol className="mb-4 space-y-1 text-sm">
                    {d.history.map((h, i) => (
                      <li key={i}>
                        <button className={`w-full rounded px-2 py-1 text-left ${picked === i ? "bg-panel font-medium" : "text-muted hover:text-ink"}`}
                          onClick={() => setPicked(i)}>
                          Change {d.history.length - i}{h.changed_at ? `, ${new Date(h.changed_at).toLocaleString()}` : ""}
                        </button>
                      </li>
                    ))}
                  </ol>
                  <div className="overflow-x-auto rounded-lg border border-rule bg-panel p-3 text-xs" aria-label="What changed">
                    {diffLines(d.history[picked].content, after(picked)).map((part, i) => (
                      <pre key={i} className={`whitespace-pre-wrap ${part.added ? "bg-approve/10 text-approve" : part.removed ? "bg-reject/10 text-reject line-through" : "text-muted"}`}>
                        {part.added ? "+ " : part.removed ? "- " : "  "}{part.value}
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
