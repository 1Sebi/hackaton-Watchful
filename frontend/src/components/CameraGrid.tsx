import { useEffect, useState } from "react";
import { API, activateCamera, getCameras, type CameraTile } from "../api";

// Live grid of the venue cameras. Each tile is the camera's MJPEG stream (the
// name + motion dot are drawn server-side). Click a tile to make it the
// AI-active camera (full detection + its own rules). One active at a time = the
// realistic budget on a CPU-only box.
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

  if (cams.length <= 1) return null; // single-camera mode: no grid needed

  return (
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
      {cams.map((c) => (
        <button
          key={c.id}
          onClick={() => click(c.id)}
          title={`${c.name}${c.persons != null ? ` · ${c.persons} persons` : ""}`}
          className={`group relative overflow-hidden rounded-lg border bg-black transition ${
            c.id === activeId ? "border-accent ring-1 ring-accent" : "border-edge hover:border-slate-500"
          }`}
        >
          <img
            src={API + `/stream/${c.id}/live.mjpg`}
            alt={c.name}
            className="block aspect-video w-full object-cover"
            onError={(e) => ((e.target as HTMLImageElement).style.opacity = "0.2")}
          />
          {c.persons != null && (
            <span className="absolute left-1 top-1 rounded bg-black/70 px-1.5 py-0.5 text-[11px] font-bold text-white">
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
  );
}
