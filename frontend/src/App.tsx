import { useEffect, useState } from "react";
import { Shell } from "./components/Shell";
import Activity from "./pages/Activity";
import Ask from "./pages/Ask";
import Graph from "./pages/Graph";
import Overview from "./pages/Overview";
import Playbook from "./pages/Playbook";
import Queue from "./pages/Queue";
import Rules from "./pages/Rules";
import Settings from "./pages/Settings";

const PAGES: Record<string, () => JSX.Element> = {
  overview: Overview, recommendations: Queue, map: Graph, rules: Rules, playbook: Playbook, ask: Ask,
  activity: Activity, settings: Settings,
};
const ALIASES: Record<string, string> = { queue: "recommendations", graph: "map" }; // old links keep working

const pageFromHash = (): string => {
  const h = window.location.hash.slice(1);
  const k = ALIASES[h] ?? h;
  return k in PAGES ? k : "overview";
};

export default function App() {
  const [page, setPage] = useState(pageFromHash);
  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const Page = PAGES[page];
  return (
    <Shell page={page}>
      <Page key={page} />
    </Shell>
  );
}
