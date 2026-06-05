import { useEffect, useState } from "react";
import { WS_BASE, type AgentState } from "../api";

export default function StatusBar() {
  const [s, setS] = useState<AgentState | null>(null);
  useEffect(() => {
    let ws: WebSocket;
    let stop = false;
    const connect = () => {
      ws = new WebSocket(WS_BASE + "/ws/state");
      ws.onmessage = (e) => setS(JSON.parse(e.data));
      ws.onclose = () => {
        if (!stop) setTimeout(connect, 1500);
      };
    };
    connect();
    return () => {
      stop = true;
      ws?.close();
    };
  }, []);

  const dot = s?.running ? "bg-accent" : "bg-red-500";
  return (
    <div className="flex items-center gap-4 text-sm">
      <span className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${dot}`} />
        {s?.running ? "live" : "offline"}
      </span>
      {s?.camera_name && (
        <span className="rounded bg-edge px-2 py-0.5 text-xs text-accent">📷 {s.camera_name}</span>
      )}
      <Stat label="FPS" value={s ? s.fps.toFixed(0) : "—"} />
      <Stat label="persons" value={s ? String(s.persons) : "—"} />
      <Stat label="rules" value={s ? String(s.conditions) : "—"} />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="text-slate-400">{label}</span>
      <span className="font-semibold text-slate-100">{value}</span>
    </span>
  );
}
