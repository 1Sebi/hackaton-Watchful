import { type AgentState } from "../api";
import { useEvents, useVenueData, type VenueData } from "../hooks/useVenueData";
import { heatFor } from "../lib/occupancy";
import GlassCard from "./ui/GlassCard";
import StatCard from "./ui/StatCard";
import HotelMap from "./HotelMap";
import ConditionsPanel from "./ConditionsPanel";

// The venue command center — landing view. Bento layout: KPI row, large venue
// map, live event feed, busiest-rooms ranking, and AI engine health. All data
// from existing endpoints (no backend change); the agent state comes from the
// shell so the header and dashboard agree.
export default function Dashboard({
  agent,
  onEnterRoom,
}: {
  agent: AgentState | null;
  onEnterRoom: (roomId: string) => void;
}) {
  const venue = useVenueData(3000);
  const events = useEvents(40);
  const todayAlerts = events.length;

  return (
    <div className="space-y-4">
      {/* KPI bento row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
        <StatCard
          label="People in venue"
          value={venue.totalPersons}
          icon="🧍"
          history={venue.personsHistory}
          color="#22d3a8"
          delay={0}
        />
        <StatCard
          label="Rooms"
          value={venue.roomsCount}
          icon="🏨"
          color="#7c8cff"
          delay={60}
        />
        <StatCard
          label="Cameras online"
          value={venue.camsOnline}
          unit={`/ ${venue.camsTotal}`}
          icon="📷"
          color="#22d3a8"
          delay={120}
        />
        <StatCard
          label="AI throughput"
          value={agent?.fps ?? 0}
          unit="fps"
          icon="⚡"
          color="#7c8cff"
          decimals={agent && agent.fps < 10 ? 1 : 0}
          delay={180}
        />
        <StatCard
          label="Alerts"
          value={todayAlerts}
          icon="🔔"
          color="#f5b343"
          delay={240}
        />
      </div>

      {/* Venue map — full width */}
      <GlassCard
        eyebrow="Venue map · live occupancy"
        right={
          <span className="text-[11px] text-slate-500">
            {venue.roomsCount} rooms · {venue.camsTotal} cameras
          </span>
        }
        delay={120}
      >
        <HotelMap
          rooms={venue.rooms}
          cameras={venue.cameras}
          activeRoom={venue.activeRoom}
          roomHistory={venue.roomHistory}
          onEnterRoom={onEnterRoom}
        />
        <p className="mt-3 text-[11px] text-slate-500">
          Click a room to focus the AI on it — full detection runs on the focused camera; other
          rooms stay light with periodic people counts.
        </p>
      </GlassCard>

      {/* Rules + recent firings — one unified section (create / pause / delete +
          what each rule has triggered). Replaces the separate Live activity card. */}
      <GlassCard
        eyebrow="Rules · tell the agent what to watch for"
        right={
          <span className="text-[11px] text-slate-500">
            type it in plain words → pick what happens
          </span>
        }
        delay={140}
      >
        <ConditionsPanel cameras={venue.cameras} events={events} />
      </GlassCard>

      {/* Lower bento: busiest rooms + AI engine health */}
      <div className="grid gap-4 lg:grid-cols-3">
        <GlassCard className="lg:col-span-2" eyebrow="Busiest rooms" delay={120}>
          <BusiestRooms venue={venue} onEnterRoom={onEnterRoom} />
        </GlassCard>
        <GlassCard eyebrow="AI engine" delay={180}>
          <AiHealth agent={agent} venue={venue} />
        </GlassCard>
      </div>
    </div>
  );
}

function BusiestRooms({
  venue,
  onEnterRoom,
}: {
  venue: VenueData;
  onEnterRoom: (id: string) => void;
}) {
  const max = Math.max(1, ...venue.busiest.map((r) => r.persons ?? 0));
  if (venue.busiest.length === 0) {
    return (
      <p className="py-6 text-center text-xs text-slate-500">
        Quiet across the venue — no occupied rooms right now.
      </p>
    );
  }
  return (
    <div className="space-y-2.5">
      {venue.busiest.map((r) => {
        const p = r.persons ?? 0;
        const heat = heatFor(p);
        return (
          <button
            key={r.id}
            onClick={() => onEnterRoom(r.id)}
            className="group flex w-full items-center gap-3 text-left"
          >
            <span className="w-28 shrink-0 truncate text-sm text-slate-200 group-hover:text-white">
              {r.name}
            </span>
            <span className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
              <span
                className="absolute inset-y-0 left-0 rounded-full transition-all duration-500"
                style={{ width: `${(p / max) * 100}%`, background: heat.dot }}
              />
            </span>
            <span className={`w-8 shrink-0 text-right text-sm font-bold tabular-nums ${heat.text}`}>
              {p}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function AiHealth({ agent, venue }: { agent: AgentState | null; venue: VenueData }) {
  const running = !!agent?.running;
  const focusRoom = venue.rooms.find((r) => r.id === venue.activeRoom);
  return (
    <div className="space-y-3">
      <Row label="Status" value={running ? "Running" : "Idle"} tone={running ? "good" : "warn"} />
      <Row label="Focus room" value={focusRoom?.name ?? "—"} />
      <Row label="Detect rate" value={agent ? `${agent.fps.toFixed(agent.fps < 10 ? 1 : 0)} fps` : "—"} />
      <Row label="Active rules" value={agent ? String(agent.conditions) : "—"} />
      <div className="mt-1 flex flex-wrap gap-1.5 pt-2">
        <span className="chip">YOLOv8</span>
        <span className="chip">Pose</span>
        <span className="chip">Moondream VLM</span>
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "good" | "warn";
}) {
  const v =
    tone === "good" ? "text-accent" : tone === "warn" ? "text-amber" : "text-slate-100";
  return (
    <div className="flex items-center justify-between border-b border-white/5 pb-2 text-sm last:border-0 last:pb-0">
      <span className="text-slate-400">{label}</span>
      <span className={`font-semibold ${v}`}>{value}</span>
    </div>
  );
}

