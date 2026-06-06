import { useEffect, useState, type ReactNode } from "react";
import StatusBar from "./components/StatusBar";
import HotelMap from "./components/HotelMap";
import RoomView from "./components/RoomView";
import ConditionEditor from "./components/ConditionEditor";
import ConditionsList from "./components/ConditionsList";
import EventLog from "./components/EventLog";
import ZoneDrawer from "./components/ZoneDrawer";
import { activateRoom, getRooms } from "./api";

type View = { kind: "map" } | { kind: "room"; roomId: string };

export default function App() {
  const [refresh, setRefresh] = useState(0);
  const [tab, setTab] = useState<"live" | "zones">("live");
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
    setRefresh((r) => r + 1);
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
                onSetActiveCam={(camId) => {
                  setActiveId(camId);
                  setRefresh((r) => r + 1);
                }}
                onBack={backToMap}
              />
              <div className="flex gap-2">
                <TabBtn active={tab === "live"} onClick={() => setTab("live")}>
                  Conditions & Events
                </TabBtn>
                <TabBtn active={tab === "zones"} onClick={() => setTab("zones")}>
                  Zones
                </TabBtn>
              </div>
              {tab === "zones" && <ZoneDrawer activeId={activeId} />}
            </>
          )}
        </section>

        <section className="space-y-4">
          {view.kind === "room" && (
            <>
              <ConditionEditor activeId={activeId} onAdded={() => setRefresh((r) => r + 1)} />
              <ConditionsList activeId={activeId} refresh={refresh} />
              <EventLog />
            </>
          )}
          {view.kind === "map" && (
            <div className="rounded-xl border border-edge bg-black/20 p-4 text-sm text-slate-400">
              <p className="mb-2 text-base font-semibold text-slate-200">How it works</p>
              <ul className="list-disc space-y-1 pl-4 text-[12px]">
                <li>Pick a room on the map to focus the AI on it.</li>
                <li>All cameras in that room get detection at once (batched YOLO).</li>
                <li>Other rooms stay light — only periodic people counts.</li>
                <li>Conditions and zones bind to a focused camera inside the room.</li>
              </ul>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

function TabBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-lg px-4 py-1.5 text-sm font-medium ${
        active ? "bg-accent text-ink" : "border border-edge text-slate-300"
      }`}
    >
      {children}
    </button>
  );
}
