import { useEffect, useState } from "react";
import { API, activateRoom, getCameras, getRooms, type CameraTile } from "../api";

// All cameras of one room shown live + with detection overlays. One of them is
// the "editing focus" (zone drawer / condition editor bind to it); clicking a
// different feed swaps that focus. Equal-sized grid — every camera is being
// analyzed by the same shared batched detector.

function gridColsFor(n: number): string {
  if (n <= 1) return "grid-cols-1";
  if (n === 2) return "grid-cols-2";
  if (n <= 4) return "grid-cols-2";
  if (n <= 6) return "grid-cols-3";
  return "grid-cols-4";
}

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
  const cols = gridColsFor(cams.length);

  const focusCam = async (camId: string) => {
    onSetActiveCam(camId);
    // tell the backend the new editing focus inside the same room
    await activateRoom(roomId, camId).catch(() => undefined);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="rounded-md border border-edge px-3 py-1 text-xs hover:border-slate-400"
          >
            ← Map
          </button>
          <div>
            <h2 className="text-xl font-bold">{roomName}</h2>
            <p className="text-[11px] text-slate-400">
              {cams.length} {cams.length === 1 ? "camera" : "cameras"} · batched detection on all
            </p>
          </div>
        </div>
        <span
          className={`rounded-lg px-3 py-1 text-sm font-bold ${
            !anyKnown
              ? "bg-black/40 text-slate-500"
              : total === 0
              ? "bg-black/40 text-slate-300"
              : total >= 5
              ? "bg-red-900/60 text-red-100"
              : "bg-emerald-900/60 text-emerald-100"
          }`}
        >
          🧍 {anyKnown ? total : "—"}
        </span>
      </div>

      {cams.length === 0 ? (
        <div className="rounded-xl border border-edge bg-black/20 p-8 text-center text-sm text-slate-400">
          No cameras configured for this room yet.
        </div>
      ) : (
        <div className={`grid auto-rows-fr gap-2 ${cols}`}>
          {cams.map((c) => (
            <button
              key={c.id}
              onClick={() => focusCam(c.id)}
              title={c.name}
              className={`group relative overflow-hidden rounded-lg border-2 bg-black transition ${
                c.id === activeId
                  ? "border-accent ring-2 ring-accent/40"
                  : "border-edge hover:border-slate-400"
              }`}
            >
              <img
                src={API + `/stream/${c.id}/live.mjpg`}
                alt={c.name}
                className="block aspect-video w-full object-cover"
                onError={(e) => ((e.target as HTMLImageElement).style.opacity = "0.2")}
              />
              <div className="absolute left-1 top-1 flex items-center gap-1">
                <span className="rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                  {c.name}
                </span>
                {c.persons != null && (
                  <span className="rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-bold text-white">
                    🧍 {c.persons}
                  </span>
                )}
              </div>
              {c.id === activeId && (
                <span className="absolute right-1 top-1 rounded bg-accent px-1.5 py-0.5 text-[10px] font-bold text-ink">
                  EDIT
                </span>
              )}
              {c.error && (
                <span className="absolute inset-x-0 bottom-0 bg-red-900/70 py-0.5 text-center text-[10px] text-red-100">
                  offline
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
