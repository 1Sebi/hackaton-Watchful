import { useEffect, useState } from "react";
import { API, activateCamera, getCameras, type CameraTile } from "../api";

// Room-grouped venue grid: ONE card per room, containing all that room's camera
// feeds at once, with a room-level people counter (sum of its cameras). Click a
// feed to make it the AI-active camera (full detection + its own rules). One
// active at a time = the realistic budget on a CPU-only box; inactive cameras
// still report a periodic per-tile count.
export default function CameraGrid({
  activeId,
  onActivate,
}: {
  activeId: string;
  onActivate: (id: string) => void;
}) {
  const [cams, setCams] = useState<CameraTile[]>([]);

  useEffect(() => {
    let stop = false;
    const tick = () =>
      getCameras()
        .then((s) => !stop && setCams(s.cameras))
        .catch(() => undefined);
    tick();
    const h = window.setInterval(tick, 3000);
    return () => {
      stop = true;
      window.clearInterval(h);
    };
  }, []);

  const click = async (id: string) => {
    onActivate(id); // optimistic
    await activateCamera(id).catch(() => undefined);
  };

  if (cams.length === 0) return null;

  // group cameras by room, preserving first-seen order
  const rooms: { room: string; cams: CameraTile[] }[] = [];
  const at = new Map<string, number>();
  for (const c of cams) {
    if (!at.has(c.room)) {
      at.set(c.room, rooms.length);
      rooms.push({ room: c.room, cams: [] });
    }
    rooms[at.get(c.room)!].cams.push(c);
  }

  // room count = sum of its cameras' counts (null if none reported yet)
  const roomCount = (rc: CameraTile[]): number | null => {
    const known = rc.filter((c) => c.persons != null);
    return known.length ? known.reduce((s, c) => s + (c.persons || 0), 0) : null;
  };

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {rooms.map(({ room, cams: rc }) => {
        const count = roomCount(rc);
        return (
          <div key={room} className="rounded-xl border border-edge bg-black/20 p-2">
            <div className="mb-2 flex items-center justify-between px-1">
              <span className="text-sm font-semibold">{room}</span>
              <span className="rounded bg-black/70 px-2 py-0.5 text-xs font-bold text-white">
                🧍 {count == null ? "—" : count}
              </span>
            </div>
            <div className={`grid gap-1 ${rc.length > 1 ? "grid-cols-2" : "grid-cols-1"}`}>
              {rc.map((c) => (
                <button
                  key={c.id}
                  onClick={() => click(c.id)}
                  title={`${c.name}${c.persons != null ? ` · ${c.persons} persons` : ""}`}
                  className={`group relative overflow-hidden rounded-lg border bg-black transition ${
                    c.id === activeId
                      ? "border-accent ring-1 ring-accent"
                      : "border-edge hover:border-slate-500"
                  }`}
                >
                  <img
                    src={API + `/stream/${c.id}/live.mjpg`}
                    alt={c.name}
                    className="block aspect-video w-full object-cover"
                    onError={(e) => ((e.target as HTMLImageElement).style.opacity = "0.2")}
                  />
                  {c.persons != null && rc.length > 1 && (
                    <span className="absolute left-1 top-1 rounded bg-black/70 px-1 text-[10px] font-bold text-white">
                      🧍 {c.persons}
                    </span>
                  )}
                  {c.id === activeId && (
                    <span className="absolute right-1 top-1 rounded bg-accent px-1 text-[10px] font-bold text-ink">
                      AI
                    </span>
                  )}
                  {c.error && (
                    <span className="absolute inset-x-0 bottom-0 bg-red-900/70 px-1 text-center text-[10px] text-red-100">
                      offline
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
