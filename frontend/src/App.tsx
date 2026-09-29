import { useCallback, useEffect, useState } from "react";
import { api, getToken, post, setOrg, setToken, type Me } from "./api";
import { Shell } from "./components/Shell";
import About from "./pages/About";
import Activity from "./pages/Activity";
import Ask from "./pages/Ask";
import Auth from "./pages/Auth";
import Execute from "./pages/Execute";
import FirstResults from "./pages/FirstResults";
import Graph from "./pages/Graph";
import Onboarding from "./pages/Onboarding";
import Overview from "./pages/Overview";
import Playbook from "./pages/Playbook";
import Profile from "./pages/Profile";
import Queue from "./pages/Queue";
import Rules from "./pages/Rules";
import ScanProgress from "./pages/ScanProgress";
import Settings from "./pages/Settings";

const ALIASES: Record<string, string> = { queue: "recommendations", graph: "map" }; // old links keep working

function route(): { page: string; arg?: string } {
  const [page = "", arg] = window.location.hash.slice(1).split("/");
  return { page: ALIASES[page] ?? page, arg };
}

export default function App() {
  const [r, setR] = useState(route);
  const [me, setMe] = useState<Me | null>(null);
  const [booting, setBooting] = useState(Boolean(getToken()));

  const adopt = useCallback((m: Me) => {
    setOrg(m.org.id);
    setMe(m);
  }, []);

  useEffect(() => {
    const onHash = () => setR(route());
    const onLogout = () => setMe(null);
    window.addEventListener("hashchange", onHash);
    window.addEventListener("cloudsense:logout", onLogout);
    if (getToken()) api<Me>("/auth/me").then(adopt, () => setToken(null)).finally(() => setBooting(false));
    return () => { window.removeEventListener("hashchange", onHash); window.removeEventListener("cloudsense:logout", onLogout); };
  }, [adopt]);

  const logout = async () => {
    await post("/auth/logout").catch(() => undefined);
    setToken(null);
    setMe(null);
    window.location.hash = "login";
  };

  if (booting) return <p className="p-10 text-muted" role="status">Loading…</p>;

  if (!me) {
    if (r.page !== "login" && r.page !== "signup") return <About />;
    return <Auth mode={r.page === "login" ? "login" : "signup"}
      onAuthed={(m) => { setToken(m.token); adopt(m); window.location.hash = m.org.settings.onboarded ? "overview" : "onboarding"; }} />;
  }

  if (!me.org.settings.onboarded) {
    return <Onboarding me={me} onDone={(scanId) => {
      api<Me>("/auth/me").then(adopt);
      window.location.hash = scanId ? `scan/${scanId}` : "overview";
    }} />;
  }

  const pages: Record<string, () => JSX.Element> = {
    overview: () => <Overview />, recommendations: () => <Queue />, map: () => <Graph />, rules: () => <Rules />,
    playbook: () => <Playbook />, ask: () => <Ask />, activity: () => <Activity />,
    settings: () => <Settings tab={r.arg} />, profile: () => <Profile onMe={adopt} onLogout={logout} />,
    scan: () => <ScanProgress scanId={r.arg ?? ""} />, results: () => <FirstResults scanId={r.arg ?? ""} />,
    execute: () => <Execute candidateId={r.arg ?? ""} />,
  };
  const page = r.page in pages ? r.page : "overview";
  const navKey = page === "scan" || page === "results" ? "overview" : page === "execute" ? "recommendations"
    : page === "profile" ? "" : page;
  return (
    <Shell page={navKey} me={me} onLogout={logout}>
      <div key={`${page}/${r.arg ?? ""}`} className="contents">{pages[page]()}</div>
    </Shell>
  );
}
