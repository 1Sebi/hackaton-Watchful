import { useState, type ReactNode } from "react";
import StatusBar from "./components/StatusBar";
import LiveView from "./components/LiveView";
import ConditionEditor from "./components/ConditionEditor";
import ConditionsList from "./components/ConditionsList";
import EventLog from "./components/EventLog";
import ZoneDrawer from "./components/ZoneDrawer";

export default function App() {
  const [refresh, setRefresh] = useState(0);
  const [tab, setTab] = useState<"live" | "zones">("live");

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
          <div className="flex gap-2">
            <TabBtn active={tab === "live"} onClick={() => setTab("live")}>
              Live
            </TabBtn>
            <TabBtn active={tab === "zones"} onClick={() => setTab("zones")}>
              Zones
            </TabBtn>
          </div>
          {tab === "live" ? <LiveView /> : <ZoneDrawer />}
        </section>

        <section className="space-y-4">
          <ConditionEditor onAdded={() => setRefresh((r) => r + 1)} />
          <ConditionsList refresh={refresh} />
          <EventLog />
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
