import { useEffect, useState } from "react";
import StatusBar from "./components/StatusBar";
import HotelMap from "./components/HotelMap";
import RoomView from "./components/RoomView";
import ZoneDrawer from "./components/ZoneDrawer";
import { activateRoom, getRooms } from "./api";
// NOTE: ConditionEditor / ConditionsList / EventLog are intentionally not
// rendered (UI hidden per user request). The components still live under
// ./components and can be re-mounted in the right column anytime.

type View = { kind: "map" } | { kind: "room"; roomId: string };

export default function App() {
  const [view, setView] = useState<View>({ kind: "map" });
  const [activeId, setActiveId] = useState("");

  // initial state: stay on the map; pick up whichever room is already active on
  // the backend so the editing focus has a sensible default if user jumps in.
  useEffect(() => {
    getRooms()
      .then((s) => {
        if (s.active_room) {
          const r = s.rooms.find((x) => x.id === s.active_room);
          if (r && r.camera_ids.length > 0) setActiveId(r.camera_ids[0]);
        }
      })
      .catch(() => undefined);
  }, []);

  const enterRoom = async (roomId: string) => {
    // optimistic: switch UI immediately, fire backend activation in the back
    setView({ kind: "room", roomId });
    const res = await activateRoom(roomId).catch(() => null);
    if (res) {
      const r = res.rooms.find((x) => x.id === roomId);
      if (r && r.camera_ids.length > 0) setActiveId(r.camera_ids[0]);
    }
  };

  const backToMap = () => {
    setView({ kind: "map" });
  };

  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-edge px-6 py-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">👁</span>
          <h1 className="text-lg font-bold">Watchful</h1>
          <span className="hidden text-xs text-slate-500 sm:inline">
            tell your camera what matters — 100% local
          </span>
        </div>
        <StatusBar />
      </header>

      <main className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-3">
        <section className="space-y-4 lg:col-span-2">
          {view.kind === "map" ? (
            <HotelMap onEnterRoom={enterRoom} />
          ) : (
            <>
              <RoomView
                roomId={view.roomId}
                activeId={activeId}
                onSetActiveCam={(camId) => setActiveId(camId)}
                onBack={backToMap}
              />
              <ZoneDrawer activeId={activeId} />
            </>
          )}
        </section>

        <section className="space-y-4">
          {view.kind === "map" && (
            <div className="rounded-xl border border-edge bg-black/20 p-4 text-sm text-slate-400">
              <p className="mb-2 text-base font-semibold text-slate-200">How it works</p>
              <ul className="list-disc space-y-1 pl-4 text-[12px]">
                <li>Pick a room on the map to focus the AI on it.</li>
                <li>All cameras in that room get detection at once (batched YOLO).</li>
                <li>Other rooms stay light — only periodic people counts.</li>
              </ul>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
