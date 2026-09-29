import { LogOut } from "lucide-react";
import { useState } from "react";
import { post, put, type Me } from "../api";
import { Banner, Field, Input } from "../components/form";
import { TopBar, useShell } from "../components/Shell";

export default function Profile({ onMe, onLogout }: { onMe: (me: Me) => void; onLogout: () => void }) {
  const { me } = useShell();
  const [name, setName] = useState(me.user.name);
  const [email, setEmail] = useState(me.user.email);
  const [pMsg, setPMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [wMsg, setWMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const saveProfile = async () => {
    setBusy(true);
    try {
      onMe(await put<Me>("/me", { name, email }));
      setPMsg({ ok: true, text: "Profile saved." });
    } catch (e) {
      setPMsg({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };
  const savePassword = async () => {
    if (next !== confirm) return setWMsg({ ok: false, text: "The new passwords don’t match." });
    setBusy(true);
    try {
      await post("/me/password", { current, new: next });
      setCurrent(""); setNext(""); setConfirm("");
      setWMsg({ ok: true, text: "Password changed. Other devices were signed out." });
    } catch (e) {
      setWMsg({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <TopBar title="Profile" subtitle={`${me.user.name} · ${me.user.role} of ${me.org.name}`} />
      <div className="flex max-w-[640px] flex-col gap-5">
        <section className="card flex flex-col gap-5 p-6">
          <h2 className="text-base font-semibold text-ink">Your details</h2>
          <Field label="Full name"><Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></Field>
          <Field label="Work email"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></Field>
          <Field label="Role"><Input readOnly value={me.user.role} className="capitalize text-muted" /></Field>
          {pMsg && <Banner kind={pMsg.ok ? "ok" : "err"} title={pMsg.text} />}
          <button className="btn btn-approve w-fit" onClick={saveProfile} disabled={busy || !name.trim() || !email.trim()}>Save profile</button>
        </section>
        <section className="card flex flex-col gap-5 p-6">
          <h2 className="text-base font-semibold text-ink">Change password</h2>
          <Field label="Current password"><Input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" /></Field>
          <Field label="New password" hint="At least 10 characters"><Input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" /></Field>
          <Field label="Confirm new password"><Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" /></Field>
          {wMsg && <Banner kind={wMsg.ok ? "ok" : "err"} title={wMsg.text} />}
          <button className="btn btn-approve w-fit" onClick={savePassword} disabled={busy || !current || next.length < 10}>Change password</button>
        </section>
        <section className="card flex items-center gap-4 p-6">
          <div className="flex-1"><h2 className="text-base font-semibold text-ink">Log out</h2><p className="text-[13px] text-muted">End your session on this device.</p></div>
          <button className="btn btn-reject" onClick={onLogout}><LogOut size={14} /> Log out</button>
        </section>
      </div>
    </>
  );
}
