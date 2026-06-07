import { type EventItem } from "../api";

// Presentational live-event list (glass rows). Fed by the `useEvents` hook from
// the parent so the dashboard and room view can share one feed component.
export default function EventFeed({
  events,
  max = 8,
  emptyHint = "No triggers yet — conditions are armed and watching.",
}: {
  events: EventItem[];
  max?: number;
  emptyHint?: string;
}) {
  const shown = events.slice(0, max);
  return (
    <div className="scroll-soft -mr-1 max-h-[22rem] space-y-2 overflow-auto pr-1">
      {shown.length === 0 && (
        <div className="flex items-center gap-2 rounded-xl border border-dashed border-white/10 px-3 py-6 text-xs text-slate-500">
          <span className="text-base">🛡️</span>
          {emptyHint}
        </div>
      )}
      {shown.map((e, i) => (
        <div
          key={e.seq ?? e.id ?? i}
          className="animate-fade-in rounded-xl border border-white/10 bg-white/[0.03] p-2.5"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-sm font-medium text-accent">
              {e.text || `condition #${e.condition_id}`}
            </span>
            <span className="shrink-0 text-[10px] tabular-nums text-slate-500">{fmtTime(e)}</span>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-slate-400">
            {e.camera_name && (
              <span className="chip !px-2 !py-0.5 !text-[10px] text-slate-300">
                📷 {e.camera_name}
              </span>
            )}
            {e.reason && <span className="truncate">{e.reason}</span>}
            {(e.action || e.action_taken) && (
              <span className="text-iris">→ {e.action || e.action_taken}</span>
            )}
            {e.confidence != null && (
              <span className="tabular-nums text-slate-500">
                {Math.round(Number(e.confidence) * 100)}%
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function fmtTime(e: EventItem): string {
  const t = e.ts ? new Date(e.ts * 1000) : e.timestamp ? new Date(e.timestamp) : null;
  return t ? t.toLocaleTimeString() : "";
}
