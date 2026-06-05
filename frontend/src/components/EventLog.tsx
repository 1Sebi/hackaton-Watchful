import { useEffect, useState } from "react";
import { type EventItem, getJSON, WS_BASE } from "../api";

export default function EventLog() {
  const [events, setEvents] = useState<EventItem[]>([]);

  useEffect(() => {
    getJSON<EventItem[]>("/events").then(setEvents).catch(() => undefined);
    let ws: WebSocket;
    let stop = false;
    const connect = () => {
      ws = new WebSocket(WS_BASE + "/ws/events");
      ws.onmessage = (e) => {
        const ev = JSON.parse(e.data) as EventItem;
        setEvents((prev) => [ev, ...prev].slice(0, 100));
      };
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

  return (
    <div className="rounded-xl border border-edge bg-panel p-4">
      <h2 className="mb-2 text-sm font-semibold text-slate-200">Event log</h2>
      <div className="max-h-72 space-y-2 overflow-auto">
        {events.length === 0 && <p className="text-xs text-slate-500">Waiting for triggers…</p>}
        {events.map((e, i) => (
          <div key={e.seq ?? e.id ?? i} className="rounded-lg border border-edge bg-ink p-2">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-sm text-accent">{e.text || `condition #${e.condition_id}`}</span>
              <span className="shrink-0 text-[11px] text-slate-500">{fmtTime(e)}</span>
            </div>
            <div className="text-[11px] text-slate-400">
              {e.camera_name && <span className="text-slate-300">📷 {e.camera_name} · </span>}
              {e.reason}
              {(e.action || e.action_taken) && <> · {e.action || e.action_taken}</>}
              {e.confidence != null && <> · conf {Number(e.confidence).toFixed(2)}</>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function fmtTime(e: EventItem): string {
  const t = e.ts ? new Date(e.ts * 1000) : e.timestamp ? new Date(e.timestamp) : null;
  return t ? t.toLocaleTimeString() : "";
}
