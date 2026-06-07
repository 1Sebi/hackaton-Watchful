import { useEffect, useState } from "react";
import { type AgentState } from "../api";
import LivePill from "./ui/LivePill";

// Global status cluster for the header: live pill, key metrics, and a clock.
// Agent state is owned by the shell (App) so the header and dashboard agree.
export default function StatusBar({ agent }: { agent: AgentState | null }) {
  const clock = useClock();
  const running = !!agent?.running;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <LivePill live={running} />
      {agent?.camera_name && (
        <span className="chip text-accent">📷 {agent.camera_name}</span>
      )}
      <div className="hidden items-center gap-1 sm:flex">
        <Metric label="people" value={agent ? String(agent.persons) : "—"} />
        <Metric label="fps" value={agent ? agent.fps.toFixed(agent.fps < 10 ? 1 : 0) : "—"} />
        <Metric label="rules" value={agent ? String(agent.conditions) : "—"} />
      </div>
      <span className="chip tabular-nums text-slate-400">{clock}</span>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex items-baseline gap-1 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1">
      <span className="text-sm font-bold tabular-nums text-slate-100">{value}</span>
      <span className="text-[10px] uppercase tracking-wide text-slate-500">{label}</span>
    </span>
  );
}

function useClock(): string {
  const [t, setT] = useState(() => new Date().toLocaleTimeString());
  useEffect(() => {
    const h = window.setInterval(() => setT(new Date().toLocaleTimeString()), 1000);
    return () => window.clearInterval(h);
  }, []);
  return t;
}
