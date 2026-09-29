import { Eye, EyeOff } from "lucide-react";
import { useState, type FormEvent } from "react";
import { post, type Me } from "../api";
import { Icon } from "../components/Icon";
import { Banner, Field, Input, Logo } from "../components/form";

type Mode = "signup" | "login";
const MIN_PASSWORD = 10;

/** Figma 02 Sign up: brand panel (560px) + form area. Log in shares the layout. */
export default function Auth({ mode, onAuthed }: { mode: Mode; onAuthed: (me: Me & { token: string }) => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const signup = mode === "signup";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (signup && password.length < MIN_PASSWORD) return setError(`Use at least ${MIN_PASSWORD} characters for your password.`);
    setBusy(true);
    try {
      const me = await post<Me & { token: string }>(signup ? "/auth/signup" : "/auth/login",
        signup ? { name, email, password } : { email, password });
      onAuthed(me);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-panel">
      <aside className="hidden w-[560px] shrink-0 flex-col bg-side-bg px-14 py-12 lg:flex">
        <Logo dark />
        <div className="flex flex-1 flex-col justify-center gap-6">
          <h1 className="text-[40px] font-bold leading-[1.05] tracking-[-0.8px] text-white">Every “no” makes it smarter.</h1>
          <p className="text-base leading-normal text-side-soft">
            Connect AWS in 5 minutes. Your team’s unwritten rules become a playbook your cost agent follows.
          </p>
          <div className="flex items-start gap-2.5 rounded-xl bg-side-raised px-4 py-3.5">
            <Icon name="sparkles" size={18} className="mt-px text-side-memory" />
            <p className="text-sm text-white">
              <span className="font-semibold text-side-memory">Rule learned:</span> DR standbys are idle by design ·
              confirmed 3×
            </p>
          </div>
        </div>
        <p className="text-[13px] text-side-text">Read-only · No credentials stored · Reversible actions</p>
      </aside>

      <main className="flex flex-1 items-center justify-center px-6 py-12">
        <form onSubmit={submit} className="flex w-full max-w-[400px] flex-col gap-5" noValidate>
          <div className="lg:hidden"><Logo /></div>
          <div className="flex flex-col gap-1.5">
            <h2 className="text-[28px] font-bold tracking-[-0.4px] text-ink">{signup ? "Create your account" : "Log in to CloudSense"}</h2>
            <p className="text-[15px] text-muted">{signup ? "Start with a free, read-only scan." : "Welcome back."}</p>
          </div>
          {error && <Banner kind="err" title={error} />}
          {signup && (
            <Field label="Full name">
              <Input autoComplete="name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Ravi Kumar" />
            </Field>
          )}
          <Field label="Work email">
            <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              placeholder="ravi@acme.io" />
          </Field>
          <Field label="Password" hint={signup ? `At least ${MIN_PASSWORD} characters` : undefined}>
            <span className="relative">
              <Input type={show ? "text" : "password"} autoComplete={signup ? "new-password" : "current-password"} required
                value={password} onChange={(e) => setPassword(e.target.value)} className="pr-10" />
              <button type="button" onClick={() => setShow(!show)} aria-label={show ? "Hide password" : "Show password"}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted hover:text-ink">
                {show ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </span>
          </Field>
          <button className="btn btn-approve h-[35px] w-full" disabled={busy || !email || !password || (signup && !name)}>
            {busy ? (signup ? "Creating account…" : "Logging in…") : signup ? "Create account" : "Log in"}
          </button>
          <p className="text-center text-sm text-muted">
            {signup ? "Already have an account? " : "New to CloudSense? "}
            <a href={signup ? "#login" : "#signup"} className="font-semibold text-approve hover:underline">
              {signup ? "Log in" : "Create an account"}
            </a>
          </p>
          {signup && <p className="text-xs text-muted">By continuing you agree to the Terms and Privacy Policy.</p>}
        </form>
      </main>
    </div>
  );
}
