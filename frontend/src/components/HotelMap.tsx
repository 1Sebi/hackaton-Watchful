import { useEffect, useState } from "react";
import { getRooms, type RoomTile } from "../api";

// Stylized venue map (not an architectural floor plan). Rooms are placed on a
// 4×5 grid in a layout that suggests the venue's logical zones — outdoor /
// entrances at the perimeter, lobby+reception central, restaurant + lounge on
// one side, jacuzzi + gym on the wellness side, conference + event hall on the
// events side, back-of-house at the back. Unknown rooms fall back to "other".
//
// Click a room → activates it (backend starts batched detection on its cameras)
// → caller routes to /room view.

const AREA: Record<string, string> = {
  Outdoor: "outdoor",
  Entrances: "entrances",
  Lounge: "lounge",
  Lobby: "lobby",
  Restaurant: "restaurant",
  Conference: "conference",
  Reception: "reception",
  Jacuzzi: "jacuzzi",
  "Event Hall": "eventhall",
  "Back-of-house": "backofhouse",
  Gym: "gym",
};

const ICON: Record<string, string> = {
  Outdoor: "🌳",
  Entrances: "🚪",
  Lounge: "🛋️",
  Lobby: "🏛️",
  Restaurant: "🍽️",
  Conference: "💼",
  Reception: "🛎️",
  Jacuzzi: "♨️",
  "Event Hall": "🎤",
  "Back-of-house": "🔧",
  Gym: "🏋️",
};

export default function HotelMap({
  onEnterRoom,
}: {
  onEnterRoom: (roomId: string) => void;
}) {
  const [rooms, setRooms] = useState<RoomTile[]>([]);
  const [activeRoom, setActiveRoom] = useState<string | null>(null);

  useEffect(() => {
    let stop = false;
    const tick = () =>
      getRooms()
        .then((s) => {
          if (stop) return;
          setRooms(s.rooms);
          setActiveRoom(s.active_room);
        })
        .catch(() => undefined);
    tick();
    const h = window.setInterval(tick, 4000);
    return () => {
      stop = true;
      window.clearInterval(h);
    };
  }, []);

  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between px-1">
        <div>
          <h2 className="text-xl font-bold">ThePlace · Venue Map</h2>
          <p className="text-xs text-slate-400">
            Click a room to open all its cameras with full detection.
          </p>
        </div>
        <span className="text-[11px] text-slate-500">
          {rooms.length} rooms · {rooms.reduce((s, r) => s + r.n_cameras, 0)} cameras
        </span>
      </div>

      <div
        className="grid gap-2"
        style={{
          gridTemplateColumns: "repeat(4, 1fr)",
          gridTemplateRows: "70px repeat(4, minmax(120px, 1fr))",
          gridTemplateAreas: `
            "outdoor outdoor outdoor outdoor"
            "entrances entrances entrances entrances"
            "lounge lobby lobby restaurant"
            "conference reception jacuzzi restaurant"
            "eventhall backofhouse backofhouse gym"
          `,
        }}
      >
        {rooms.map((r) => {
          const area = AREA[r.name] ?? "outdoor";
          const icon = ICON[r.name] ?? "📍";
          const isActive = r.id === activeRoom;
          return (
            <button
              key={r.id}
              style={{ gridArea: area }}
              onClick={() => onEnterRoom(r.id)}
              className={`group relative flex flex-col items-start justify-between rounded-xl border-2 p-3 text-left transition ${
                isActive
                  ? "border-accent bg-accent/10 ring-2 ring-accent/40"
                  : "border-edge bg-black/30 hover:border-slate-400 hover:bg-black/40"
              }`}
            >
              <div className="flex w-full items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-2xl leading-none">{icon}</span>
                  <span className="text-sm font-semibold">{r.name}</span>
                </div>
                {isActive && (
                  <span className="rounded bg-accent px-1.5 py-0.5 text-[10px] font-bold text-ink">
                    AI
                  </span>
                )}
              </div>

              <div className="flex w-full items-end justify-between">
                <span className="text-[11px] text-slate-400">
                  {r.n_cameras} {r.n_cameras === 1 ? "camera" : "cameras"}
                </span>
                <span
                  className={`rounded-md px-2 py-0.5 text-sm font-bold ${
                    r.persons === null
                      ? "bg-black/40 text-slate-500"
                      : r.persons === 0
                      ? "bg-black/40 text-slate-300"
                      : r.persons >= 5
                      ? "bg-red-900/60 text-red-100"
                      : "bg-emerald-900/60 text-emerald-100"
                  }`}
                >
                  🧍 {r.persons === null ? "—" : r.persons}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      <p className="px-1 text-[11px] text-slate-500">
        Detection runs only on the room you open — heavy models stay focused on what you're watching.
      </p>
    </div>
  );
}
