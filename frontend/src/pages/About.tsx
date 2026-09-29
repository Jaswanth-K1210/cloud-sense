import { Check, Clock, GitBranch, Hash, Lock, Plus, Server, Undo2, User as UserIcon, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Icon } from "../components/Icon";
import { Logo } from "../components/form";

/** Figma 01 About page (public landing). Copy follows the Figma file and docs/UI_WORKFLOW.md section 1. */

const REPO = "https://github.com/Jaswanth-K1210/cloud-sense";
const go = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
const start = () => { window.location.hash = "signup"; };

function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="text-[13px] font-semibold tracking-[0.8px] text-approve">{children}</p>;
}

function SectionHead({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: string }) {
  return (
    <div className="flex max-w-[760px] flex-col gap-3">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 className="text-[38px] font-bold leading-[1.15] tracking-[-0.8px] text-ink">{title}</h2>
      {sub && <p className="text-lg leading-[1.45] text-muted">{sub}</p>}
    </div>
  );
}

function Section({ id, tint, children }: { id?: string; tint?: boolean; children: ReactNode }) {
  return (
    <section id={id} className={`scroll-mt-20 px-6 py-24 lg:px-20 ${tint ? "bg-paper" : "bg-panel"}`}>
      <div className="mx-auto flex max-w-[1280px] flex-col gap-12">{children}</div>
    </section>
  );
}

function IconTile({ children, tone = "approve" }: { children: ReactNode; tone?: "approve" | "learned" | "warn" | "reject" | "ink" }) {
  const c = { approve: "bg-approve/10 text-approve", learned: "bg-learned-soft text-learned", warn: "bg-warn-soft text-warn",
    reject: "bg-reject/10 text-reject", ink: "bg-track text-ink" }[tone];
  return <span className={`flex size-10 items-center justify-center rounded-[10px] ${c}`}>{children}</span>;
}

function SlackBtn({ kind, children }: { kind: "approve" | "reject" | "plain"; children: ReactNode }) {
  const c = kind === "approve" ? "border-approve bg-approve text-white" : kind === "reject" ? "border-reject/60 text-reject" : "border-rule text-ink";
  return <span className={`rounded-md border px-3 py-1 text-[13px] font-semibold ${c}`}>{children}</span>;
}

function HeroDemo() {
  const step = (n: number) => ({ animationDelay: `${n * 0.9}s` });
  return (
    <div className="flex w-full max-w-[540px] flex-col gap-3.5" aria-label="Example: CloudSense learning from a rejection in Slack">
      <div className="card animate-rise p-5 shadow-sm" style={step(0)}>
        <div className="flex items-center gap-2">
          <span className="flex size-[26px] items-center justify-center rounded-md bg-approve text-white"><Icon name="cloud" size={18} /></span>
          <span className="text-sm font-bold text-ink">CloudSense</span>
          <span className="rounded bg-track px-1 text-[10px] font-semibold text-muted">APP</span>
          <span className="text-xs text-muted">9:41 AM</span>
        </div>
        <div className="mt-2.5 flex flex-col gap-1 pl-[34px] text-[15px] text-ink">
          <p className="font-semibold">Stop orders-db-standby: save $41/mo</p>
          <p className="text-[14px]"><span className="font-medium">Why flagged:</span> 0% CPU for 14 days · no network traffic</p>
          <p className="text-[14px]"><span className="font-medium">Blast radius:</span> 1 dependent · acme-prod · us-east-1</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <SlackBtn kind="approve">Approve</SlackBtn><SlackBtn kind="reject">Reject</SlackBtn>
            <SlackBtn kind="plain">Snooze 30d</SlackBtn><SlackBtn kind="plain">Why?</SlackBtn>
          </div>
        </div>
      </div>
      <div className="card animate-rise p-5 shadow-sm" style={step(1)}>
        <div className="flex items-start gap-2">
          <span className="flex size-[26px] items-center justify-center rounded-md bg-side-avatar text-[11px] font-semibold text-white">RK</span>
          <div className="flex flex-col gap-1">
            <p className="flex items-baseline gap-2"><span className="text-sm font-bold text-ink">Ravi Kumar</span><span className="text-xs text-muted">9:42 AM</span></p>
            <p className="text-[15px] text-ink">It’s the DR standby for orders-db, idle on purpose.</p>
          </div>
        </div>
      </div>
      <div className="animate-rise flex items-start gap-2.5 rounded-[10px] bg-learned-soft/70 px-3.5 py-3" style={step(2)}>
        <Icon name="sparkles" size={18} className="mt-px text-learned" />
        <div className="flex flex-col gap-0.5">
          <p className="text-sm font-semibold text-learned">Rule learned: DR standbys are idle by design</p>
          <p className="text-[13px] text-ink">Confirmed 1× · applies to all accounts</p>
        </div>
      </div>
      <div className="card animate-rise flex items-center gap-3 px-4 py-3.5 shadow-sm" style={step(3)}>
        <Icon name="eye" size={18} className="text-muted" />
        <div className="flex flex-1 flex-col gap-0.5">
          <p className="text-sm font-semibold text-ink">Next scan: payments-db-standby skipped</p>
          <p className="text-xs text-muted">Matches the rule above. No message sent.</p>
        </div>
        <span className="rounded-full bg-learned-soft px-2 py-0.5 text-xs font-medium text-learned">Learned rule</span>
      </div>
    </div>
  );
}

// Sample data from the evaluation harness (as labelled in the design).
const WITH = [58, 64, 71, 76, 80, 84, 87, 89, 91, 93];
const WITHOUT = [57, 59, 56, 60, 58, 61, 57, 60, 59, 58];
const PX = 2.1; // Figma: 93% -> 195px

function LoopChart() {
  return (
    <figure className="card flex min-w-0 flex-1 flex-col gap-6 p-7" aria-label="Acceptance rate per scan, with and without memory">
      <div className="flex flex-wrap items-center gap-5">
        <p className="flex-1 text-base font-semibold text-ink">Acceptance rate per scan</p>
        <span className="flex items-center gap-1.5 text-xs text-muted"><span className="size-2.5 rounded-full bg-approve" /> With memory</span>
        <span className="flex items-center gap-1.5 text-xs text-muted"><span className="size-2.5 rounded-full bg-approve-soft" /> Without memory</span>
      </div>
      <div className="flex h-[240px] items-end justify-between gap-1 overflow-x-auto">
        {WITH.map((w, i) => (
          <div key={i} className="flex flex-col items-center gap-2" title={`Scan ${i + 1}: ${w}% with memory, ${WITHOUT[i]}% without`}>
            {i === WITH.length - 1 && <span className="text-[11px] font-semibold text-approve">{w}%</span>}
            <div className="flex items-end gap-1">
              <span className="w-4 rounded-t bg-approve-soft" style={{ height: WITHOUT[i] * PX }} />
              <span className="w-4 rounded-t bg-approve" style={{ height: w * PX }} />
            </div>
            <span className="whitespace-nowrap text-[11px] text-muted">Scan {i + 1}</span>
          </div>
        ))}
      </div>
      <figcaption className="text-[13px] text-muted">Rejections dropped from 8 to 1 per scan as rules were learned. Sample data from the evaluation harness.</figcaption>
    </figure>
  );
}

function RuleCard() {
  return (
    <div className="card flex w-full flex-col gap-4 p-7 lg:w-[440px]">
      <p className="flex items-center gap-2 text-xs font-semibold tracking-[0.8px] text-learned"><Icon name="sparkles" size={16} /> LEARNED RULE</p>
      <p className="text-[22px] font-bold tracking-[-0.3px] text-ink">DR standbys are idle by design</p>
      <div className="flex flex-wrap gap-2">
        {["Confirmed 3×", "Payments team", "All accounts"].map((t) => <span key={t} className="rounded-full bg-track px-2.5 py-0.5 text-xs font-medium text-ink">{t}</span>)}
      </div>
      <div className="h-px bg-rule" />
      <p className="text-[11px] font-semibold tracking-[0.8px] text-muted">SOURCE</p>
      <div>
        <p className="text-base italic text-ink">“That’s the standby for orders-db, don’t touch it.”</p>
        <p className="mt-1 text-xs text-muted">Ravi Kumar · Sep 28</p>
      </div>
      <div className="flex items-start gap-2.5 rounded-[10px] bg-success/10 px-3.5 py-3">
        <Check size={18} className="text-success" />
        <div><p className="text-sm font-semibold text-success">Protected 2 resources this week</p><p className="text-[13px] text-ink">payments-db-standby, reporting-db-standby</p></div>
      </div>
    </div>
  );
}

const FAQ: [string, string][] = [
  ["Do you need write access?", "No. CloudSense is read-only by default. Actions need a separate, optional role you can remove any time."],
  ["What if it learns a wrong rule?", "Every rule shows who taught it, when, and the exact words. Admins can delete any rule, and CloudSense stops applying it on the next scan."],
  ["How long until it’s useful?", "Your first scan takes about a minute. Learning becomes noticeable after your team’s first few reviews."],
  ["Which AWS services are supported?", "EC2, EBS volumes and snapshots, Elastic IPs, RDS and S3 today."],
  ["Where is my data stored?", "In your workspace’s isolated memory. CloudSense never stores AWS credentials; it uses a read-only role you control."],
];

export default function About() {
  const [open, setOpen] = useState(0);
  return (
    <div className="bg-panel text-ink">
      <header className="sticky top-0 z-20 border-b border-rule bg-panel/95 backdrop-blur">
        <div className="mx-auto flex h-[75px] max-w-[1280px] items-center gap-10 px-6 lg:px-0">
          <a href="#about" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}><Logo /></a>
          <nav aria-label="Sections" className="hidden gap-8 md:flex">
            {[["how", "How it works"], ["safety", "Safety"], ["pricing", "Pricing"], ["faq", "FAQ"]].map(([id, label]) => (
              <button key={id} onClick={() => go(id)} className="text-[15px] font-medium text-muted hover:text-ink">{label}</button>
            ))}
          </nav>
          <span className="flex-1" />
          <a href="#login" className="text-[15px] font-medium text-ink hover:text-approve">Log in</a>
          <button className="btn btn-approve h-[35px] px-4" onClick={start}>Start free scan</button>
        </div>
      </header>

      <section className="px-6 pb-24 pt-20 lg:px-20">
        <div className="mx-auto flex max-w-[1280px] flex-wrap items-center justify-between gap-16">
          <div className="flex max-w-[676px] flex-col gap-6">
            <span className="flex w-fit items-center gap-1.5 rounded-full bg-learned-soft px-2.5 py-1 text-[13px] font-medium text-learned">
              <Icon name="sparkles" size={12} /> AWS cost agent with memory
            </span>
            <h1 className="text-[52px] font-bold leading-[1.07] tracking-[-1.6px] text-ink">
              Cost tools tell you what to delete. CloudSense learns what you’ll never let it delete.
            </h1>
            <p className="text-xl leading-[1.45] text-muted">
              An AWS cost agent that learns your team’s unwritten rules from every “no”, so its recommendations get more
              trustworthy every week.
            </p>
            <div className="flex flex-wrap gap-3">
              <button className="btn btn-approve h-[45px] px-5 text-[15px]" onClick={start}>Start free scan</button>
              <button className="btn h-[47px] px-5 text-[15px]" onClick={() => go("loop")}>Watch 2-min demo</button>
            </div>
            <div className="flex flex-wrap gap-6 text-[13px] text-muted">
              <span className="flex items-center gap-1.5"><Lock size={15} /> Read-only access</span>
              <span className="flex items-center gap-1.5"><Icon name="shield" size={15} /> No credentials stored</span>
              <span className="flex items-center gap-1.5"><Undo2 size={15} /> Every action reversible</span>
            </div>
          </div>
          <HeroDemo />
        </div>
      </section>

      <Section tint>
        <SectionHead eyebrow="THE PROBLEM" title="Recommendations fail because they lack context"
          sub="Every cost tool can spot an idle server. None of them know why it exists." />
        <div className="grid gap-6 md:grid-cols-3">
          {([[<Icon key="a" name="alert" size={20} />, "warn", "“Idle” isn’t useless", "The DR standby, the month-end payroll job, the legal archive: all look like waste on a CPU graph."],
            [<X key="x" size={20} />, "reject", "Bad suggestions kill trust", "After a few wrong recommendations, engineers mute the channel and real savings never happen."],
            [<UserIcon key="u" size={20} />, "learned", "The context lives in people’s heads", "Nobody writes down why a resource exists, until they say it while rejecting a suggestion."]] as const).map(([icon, tone, title, body]) => (
            <div key={title} className="card flex flex-col gap-3 p-6">
              <IconTile tone={tone}>{icon}</IconTile>
              <h3 className="mt-3 text-lg font-semibold text-ink">{title}</h3>
              <p className="text-[15px] leading-[1.5] text-muted">{body}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section id="how">
        <SectionHead eyebrow="HOW IT WORKS" title="From first scan to a team that trusts its cost agent" />
        <ol className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
          {[["Connect", "One-click read-only AWS role. No keys, no passwords.", "5 minutes"],
            ["Scan", "Finds idle servers, unused disks, oversized machines and old snapshots, with dollar value and blast radius.", "~60 seconds"],
            ["Review", "Approve or reject in Slack. Rejecting takes one sentence of why.", "1 click"],
            ["Learn", "Every “no” becomes a rule with evidence. Look-alikes are skipped automatically, with the reason shown.", "Every review"]].map(([title, body, time], i) => (
            <li key={title} className="card flex flex-col gap-3 p-6">
              <span className="flex size-10 items-center justify-center rounded-[10px] bg-ink text-base font-bold text-white">{i + 1}</span>
              <h3 className="mt-3 text-lg font-semibold text-ink">{title}</h3>
              <p className="flex-1 text-[15px] leading-[1.5] text-muted">{body}</p>
              <span className="flex w-fit items-center gap-1 rounded-full bg-track px-2.5 py-0.5 text-xs font-medium text-ink"><Clock size={12} /> {time}</span>
            </li>
          ))}
        </ol>
      </Section>

      <Section id="loop" tint>
        <SectionHead eyebrow="THE LEARNING LOOP" title="It gets better every week, and you can measure it"
          sub="Acceptance rate = approved ÷ reviewed. Same accounts, same agent, with and without memory." />
        <div className="flex flex-wrap items-start gap-6"><LoopChart /><RuleCard /></div>
      </Section>

      <Section>
        <SectionHead eyebrow="FEATURES" title="Everything a team needs to trust automated savings" />
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {([[<Icon key="s" name="sparkles" size={20} />, "learned", "Learned Rules", "Every rejection becomes a rule, with who taught it and how often it’s been confirmed."],
            [<Icon key="b" name="book" size={20} />, "approve", "Team Playbook", "An auto-written, versioned “what we never touch and why” document."],
            [<Icon key="n" name="net" size={20} />, "approve", "Blast radius", "See every dependent resource before anything changes."],
            [<Hash key="h" size={20} />, "approve", "Slack-native", "Approve or reject where your engineers already work."],
            [<Icon key="m" name="msg" size={20} />, "approve", "Ask anything", "“Can we downsize the payroll servers?” Answers cite past decisions."],
            [<Undo2 key="u" size={20} />, "approve", "Safe actions", "Backup first, then stop. One-click undo. Terraform gets a diff, not a change."]] as const).map(([icon, tone, title, body]) => (
            <div key={title} className="card flex flex-col gap-3 p-6">
              <IconTile tone={tone}>{icon}</IconTile>
              <h3 className="mt-3 text-lg font-semibold text-ink">{title}</h3>
              <p className="text-[15px] leading-[1.5] text-muted">{body}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section id="safety" tint>
        <SectionHead eyebrow="SAFETY" title="Built so nothing breaks, and nothing is hidden" />
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {([[<Lock key="l" size={20} />, "Read-only by default", "Write access is a separate, optional permission."],
            [<Icon key="e" name="eye" size={20} />, "Dry run first", "See the exact AWS calls before anything runs."],
            [<Undo2 key="u" size={20} />, "Reversible actions", "Snapshot before stop or delete. Undo on every action."],
            [<GitBranch key="g" size={20} />, "Infrastructure-as-code respected", "Terraform and CloudFormation resources get a code diff, never a live change."],
            [<Icon key="s" name="shield" size={20} />, "You control the memory", "See where every rule came from. Admins can delete any rule."],
            [<Server key="v" size={20} />, "Tenant isolation", "Each workspace has its own private memory."]] as const).map(([icon, title, body]) => (
            <div key={title} className="card flex flex-col gap-2 p-6">
              <span className="text-approve">{icon}</span>
              <h3 className="mt-1 text-base font-semibold text-ink">{title}</h3>
              <p className="text-[15px] leading-[1.45] text-muted">{body}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section>
        <SectionHead eyebrow="HOW IT’S DIFFERENT" title="Detection is solved. Trust isn’t." />
        <div className="max-w-[900px] overflow-x-auto rounded-xl border border-rule">
          <table className="w-full text-[15px]">
            <thead>
              <tr className="text-sm font-semibold text-ink">
                <th className="px-6 py-4 text-left font-medium text-muted"><span className="sr-only">Capability</span></th>
                <th className="w-[200px] px-6 text-center">Typical cost tools</th>
                <th className="w-[200px] bg-approve/5 px-6 text-center text-approve">CloudSense</th>
              </tr>
            </thead>
            <tbody>
              {[["Finds waste", true], ["Learns from why you rejected", false], ["Skips look-alikes it has never seen", false],
                ["Shows the evidence behind every skip", false], ["Writes your team’s playbook", false]].map(([label, typical]) => (
                <tr key={String(label)} className="border-t border-rule">
                  <td className="px-6 py-4 text-ink">{label}</td>
                  <td className="px-6 text-center">{typical
                    ? <span className="inline-flex size-6 items-center justify-center rounded-full bg-success/10 text-success"><Check size={14} aria-label="Yes" /></span>
                    : <span className="inline-flex size-6 items-center justify-center rounded-full bg-track text-muted"><X size={14} aria-label="No" /></span>}</td>
                  <td className="bg-approve/5 px-6 text-center"><span className="inline-flex size-6 items-center justify-center rounded-full bg-success/10 text-success"><Check size={14} aria-label="Yes" /></span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section id="pricing" tint>
        <SectionHead eyebrow="PRICING" title="Start free. Pay when it’s saving you money." />
        <div className="grid items-start gap-6 lg:grid-cols-3">
          {([["Free scan", "$0", "One account, one scan", ["Full waste report", "Blast radius for every finding", "Read-only access"], "Start free scan", false],
            ["Team", "Per account", "Billed monthly", ["Slack reviews", "Learned rules & playbook", "Safe actions with undo", "Ask, with citations"], "Start free scan", true],
            ["Enterprise", "Custom", "For large AWS estates", ["SSO & audit export", "Self-hosted memory option", "Custom limits & SLAs"], "Contact us", false]] as const).map(([name, price, sub, items, cta, hot]) => (
            <div key={name} className={`card flex flex-col gap-4 p-7 ${hot ? "border-approve ring-1 ring-approve" : ""}`}>
              <div className="flex items-center"><p className="flex-1 text-base font-semibold text-ink">{name}</p>
                {hot && <span className="rounded-full bg-approve/10 px-2.5 py-0.5 text-xs font-semibold text-approve">Most popular</span>}</div>
              <p className="text-[34px] font-bold tracking-[-0.6px] text-ink">{price}</p>
              <p className="-mt-2 text-sm text-muted">{sub}</p>
              <div className="h-px bg-rule" />
              <ul className="flex flex-col gap-3">{items.map((i) => <li key={i} className="flex items-center gap-2 text-sm text-ink"><Check size={16} className="text-approve" /> {i}</li>)}</ul>
              {cta === "Contact us"
                ? <a className="btn h-[37px] w-full" href={REPO} target="_blank" rel="noreferrer">Contact us</a>
                : <button className={`btn h-[37px] w-full ${hot ? "btn-approve" : ""}`} onClick={start}>{cta}</button>}
            </div>
          ))}
        </div>
      </Section>

      <Section id="faq">
        <SectionHead eyebrow="FAQ" title="Questions teams ask before connecting AWS" />
        <div className="max-w-[900px] divide-y divide-rule rounded-xl border border-rule">
          {FAQ.map(([q, a], i) => (
            <div key={q} className="px-6 py-5">
              <button className="flex w-full items-center gap-4 text-left" aria-expanded={open === i} onClick={() => setOpen(open === i ? -1 : i)}>
                <span className="flex-1 text-base font-semibold text-ink">{q}</span>
                {open === i ? <X size={18} className="text-muted" /> : <Plus size={18} className="text-muted" />}
              </button>
              {open === i && <p className="mt-3 text-[15px] leading-[1.5] text-muted">{a}</p>}
            </div>
          ))}
        </div>
      </Section>

      <section className="bg-side-bg px-6 py-20 text-center">
        <h2 className="text-[40px] font-bold tracking-[-0.8px] text-white">Find your waste in 5 minutes.</h2>
        <p className="mt-4 text-base text-side-soft">Read-only scan. No credentials stored. Cancel any time.</p>
        <button className="btn mt-7 h-[45px] border-white bg-white px-6 text-[15px] text-ink hover:opacity-90" onClick={start}>Start free scan</button>
      </section>

      <footer className="px-6 py-8 lg:px-20">
        <div className="mx-auto flex max-w-[1280px] flex-wrap items-center gap-7">
          <Logo />
          <span className="flex-1" />
          {[["Docs", "https://github.com/Jaswanth-K1210/cloud-sense#readme"], ["GitHub", REPO],
            ["Security", "#safety"], ["Privacy", "#faq"], ["Contact", REPO]].map(([label, href]) => (
            href.startsWith("#")
              ? <button key={label} className="text-sm text-muted hover:text-ink" onClick={() => go(href.slice(1))}>{label}</button>
              : <a key={label} href={href} target={href.startsWith("http") ? "_blank" : undefined} rel="noreferrer" className="text-sm text-muted hover:text-ink">{label}</a>
          ))}
          <span className="text-sm text-muted">© 2026 CloudSense</span>
        </div>
      </footer>
    </div>
  );
}
