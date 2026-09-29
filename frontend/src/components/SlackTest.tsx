import { Send } from "lucide-react";
import { useState } from "react";
import { ORG, post, put } from "../api";
import { Banner } from "./form";

/** Saves the channel, then posts a test message there and shows Slack's answer with the exact fix. */
export function SlackTest({ channel }: { channel: string }) {
  const [state, setState] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const send = async () => {
    setBusy(true);
    setState(null);
    try {
      await put(`/orgs/${ORG}/settings`, { slack: { channel } });
      const r = await post<{ message: string }>(`/orgs/${ORG}/slack/test`);
      setState({ ok: true, text: r.message });
    } catch (e) {
      setState({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex flex-col gap-2">
      <button type="button" className="btn w-fit" onClick={send} disabled={busy || !channel.trim()}>
        <Send size={14} /> {busy ? "Sending…" : "Send test message"}
      </button>
      {state && <Banner kind={state.ok ? "ok" : "err"} title={state.text} />}
    </div>
  );
}
