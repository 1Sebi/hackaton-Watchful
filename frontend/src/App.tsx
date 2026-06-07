import { useEffect, useState } from "react";
import StatusBar from "./components/StatusBar";
import Logo from "./components/ui/Logo";
import Dashboard from "./components/Dashboard";
import RoomView from "./components/RoomView";
import { activateRoom, getRooms } from "./api";
import { useAgentState } from "./hooks/useVenueData";
// NOTE: ConditionEditor / ConditionsList live under ./components and can be
// re-mounted in the room view's right rail anytime.

type View = { kind: "map" } | { kind: "room"; roomId: string };

export default function App() {
  const [view, setView] = useState<View>({ kind: "map" });
  const [activeId, setActiveId] = useState("");
  const agent = useAgentState();

  // pick up whichever room is already active on the backend so the editing
  // focus has a sensible default if the user jumps straight into a room.
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
    setView({ kind: "room", roomId }); // optimistic
    const res = await activateRoom(roomId).catch(() => null);
    if (res) {
      const r = res.rooms.find((x) => x.id === roomId);
      if (r && r.camera_ids.length > 0) setActiveId(r.camera_ids[0]);
    }
  };

  const backToMap = () => setView({ kind: "map" });

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-white/10 bg-base/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1500px] flex-wrap items-center justify-between gap-3 px-5 py-3">
          <div className="flex items-center gap-4">
            <Logo />
            <span className="hidden h-8 w-px bg-white/10 sm:block" />
            <div className="hidden flex-col leading-tight sm:flex">
              <span className="flex items-center gap-1.5 text-sm font-bold text-white">
                <span className="text-base">👁</span> Watchful
              </span>
            </div>
          </div>
          <StatusBar agent={agent} />
        </div>
      </header>

      <main className="mx-auto max-w-[1500px] px-5 py-5">
        {view.kind === "map" ? (
          <Dashboard agent={agent} onEnterRoom={enterRoom} />
        ) : (
          <RoomView
            roomId={view.roomId}
            activeId={activeId}
            onSetActiveCam={setActiveId}
            onBack={backToMap}
          />
        )}
      </main>
    </div>
  );
}
