import { useEffect, useState } from "react";
import { api, currentUserId, ORG, setCurrentUserId, type User } from "./api";
import Overview from "./pages/Overview";
import Queue from "./pages/Queue";
import Graph from "./pages/Graph";
import Rules from "./pages/Rules";
import Playbook from "./pages/Playbook";
import Ask from "./pages/Ask";
import Settings from "./pages/Settings";

const PAGES = {
  overview: { label: "Overview", el: Overview },
  queue: { label: "Queue", el: Queue },
  graph: { label: "Graph", el: Graph },
  rules: { label: "Learned rules", el: Rules },
  playbook: { label: "Playbook", el: Playbook },
  ask: { label: "Ask", el: Ask },
  settings: { label: "Settings", el: Settings },
} as const;
type PageKey = keyof typeof PAGES;

const pageFromHash = (): PageKey => {
  const h = window.location.hash.slice(1);
  return (h in PAGES ? h : "overview") as PageKey;
};

export default function App() {
  const [page, setPage] = useState<PageKey>(pageFromHash);
  const [users, setUsers] = useState<User[]>([]);
  const [userId, setUserId] = useState(currentUserId);

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    api<User[]>(`/orgs/${ORG}/users`).then(setUsers, () => setUsers([]));
  }, []);

  const Page = PAGES[page].el;
  return (
    <div className="min-h-screen">
      <header className="border-b border-rule bg-panel">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <a href="#overview" className="text-lg font-bold tracking-tight">CloudSense</a>
          <nav aria-label="Pages" className="flex flex-wrap gap-1">
            {(Object.keys(PAGES) as PageKey[]).map((k) => (
              <a key={k} href={`#${k}`} aria-current={page === k ? "page" : undefined}
                className={`rounded px-2.5 py-1 text-sm ${page === k ? "bg-paper font-semibold" : "text-muted hover:text-ink"}`}>
                {PAGES[k].label}
              </a>
            ))}
          </nav>
          <label className="ml-auto flex items-center gap-2 text-sm text-muted">
            Acting as
            <select className="field w-auto py-1" value={userId}
              onChange={(e) => { setCurrentUserId(e.target.value); setUserId(e.target.value); }}>
              {users.length === 0 && <option value={userId}>{userId}</option>}
              {users.map((u) => <option key={u.id} value={u.id}>{u.name} ({u.role})</option>)}
            </select>
          </label>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Page key={`${page}-${userId}`} />
      </main>
    </div>
  );
}
