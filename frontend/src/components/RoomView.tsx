import { useEffect, useMemo, useState } from "react";
import { API, activateRoom, getCameras, getRooms, type CameraTile } from "../api";
import { fmtPersons, heatFor } from "../lib/occupancy";
import { useEvents } from "../hooks/useVenueData";
import GlassCard from "./ui/GlassCard";
import LiveView from "./LiveView";
import EventFeed from "./EventFeed";

// One room, focused. The selected FOCUS camera streams big (4K main, full
// detection); the room's other cameras appear as a thumbnail rail (light 360p
// sub-stream, periodic counts). Clicking a thumbnail swaps the focus. Right rail
// shows this room's live events.
export default function RoomView({
  roomId,
  activeId,
  onSetActiveCam,
  onBack,
}: {
  roomId: string;
  activeId: string;
  onSetActiveCam: (camId: string) => void;
  onBack: () => void;
}) {
  const [cams, setCams] = useState<CameraTile[]>([]);
  const [roomName, setRoomName] = useState<string>(roomId);
  const allEvents = useEvents(60);

  useEffect(() => {
    let stop = false;
    const tick = () =>
      Promise.all([getCameras(), getRooms()])
        .then(([cs, rs]) => {
          if (stop) return;
          const r = rs.rooms.find((x) => x.id === roomId);
          setRoomName(r?.name ?? roomId);
          setCams(cs.cameras.filter((c) => c.room === roomId));
        })
        .catch(() => undefined);
    tick();
    const h = window.setInterval(tick, 3000);
    return () => {
      stop = true;
      window.clearInterval(h);
    };
  }, [roomId]);

  const total = cams.reduce((s, c) => s + (c.persons ?? 0), 0);
  const anyKnown = cams.some((c) => c.persons != null);
  const heat = heatFor(anyKnown ? total : null);
  const focus = cams.find((c) => c.id === activeId) ?? cams[0];
  const others = cams.filter((c) => c.id !== focus?.id);

  const roomCamIds = useMemo(() => new Set(cams.map((c) => c.id)), [cams]);
  const roomEvents = allEvents.filter(
    (e) => !e.camera_id || roomCamIds.has(e.camera_id)
  );

  const focusCam = async (camId: string) => {
    onSetActiveCam(camId);
    await activateRoom(roomId, camId).catch(() => undefined);
  };

  return (
    <div className="space-y-4">
      {/* Room header */}
      <div className="glass animate-fade-up flex flex-wrap items-center justify-between gap-3 p-3">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-white/25 hover:bg-white/[0.07]"
          >
            ← Venue map
          </button>
          <div>
            <h2 className="font-display text-xl font-black tracking-tight">{roomName}</h2>
            <p className="text-[11px] text-slate-400">
              {cams.length} {cams.length === 1 ? "camera" : "cameras"} · full detection on the
              focused feed
            </p>
          </div>
        </div>
        <span
          className={`rounded-xl border px-3 py-1.5 text-sm font-bold tabular-nums ${heat.bg} ${heat.ring} ${heat.text}`}
        >
          🧍 {anyKnown ? total : "—"} in room
        </span>
      </div>

      {cams.length === 0 ? (
        <GlassCard>
          <p className="py-10 text-center text-sm text-slate-400">
            No cameras configured for this room yet.
          </p>
        </GlassCard>
      ) : (
        <div className="grid gap-4 xl:grid-cols-3">
          {/* Focus feed + thumbnail rail */}
          <div className="space-y-3 xl:col-span-2">
            {focus && <LiveView activeId={focus.id} label={focus.name} />}
            {others.length > 0 && (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
                {others.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => focusCam(c.id)}
                    title={c.name}
                    className="group relative overflow-hidden rounded-xl border border-white/10 bg-black transition hover:-translate-y-0.5 hover:border-white/30"
                  >
                    <img
                      src={API + `/stream/${c.id}/live.mjpg`}
                      alt={c.name}
                      className="block aspect-video w-full object-cover"
                      onError={(e) => ((e.target as HTMLImageElement).style.opacity = "0.2")}
                    />
                    <span className="absolute left-1 top-1 max-w-[80%] truncate rounded bg-black/65 px-1.5 py-0.5 text-[10px] font-medium text-white backdrop-blur">
                      {c.name}
                    </span>
                    {c.persons != null && (
                      <span className="absolute right-1 top-1 rounded bg-black/65 px-1.5 py-0.5 text-[10px] font-bold text-white backdrop-blur">
                        🧍 {c.persons}
                      </span>
                    )}
                    {c.error && (
                      <span className="absolute inset-x-0 bottom-0 bg-danger/70 py-0.5 text-center text-[10px] text-white">
                        offline
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Right rail: live events for this room */}
          <div className="space-y-4">
            <GlassCard eyebrow="Room activity" delay={120}>
              <EventFeed
                events={roomEvents}
                max={10}
                emptyHint="No triggers in this room yet."
              />
            </GlassCard>
          </div>
        </div>
      )}
    </div>
  );
}
