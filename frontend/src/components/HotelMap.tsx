import { type CameraTile, type RoomTile } from "../api";
import { fmtPersons, heatFor } from "../lib/occupancy";

// Venue occupancy board. Uniform responsive grid of EQUAL room cards (no more
// hardcoded bento areas with mismatched sizes / empty space): cards wrap to fit
// the width and are sorted busiest-first so the hottest rooms bubble to the top.
// The AI-focused room is highlighted. Click a room → focuses detection on it.
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

// Occupancy at which the density meter reads "full" (mirrors lib/occupancy heat).
const DENSITY_CAP = 10;

export default function HotelMap({
  rooms,
  cameras,
  activeRoom,
  roomHistory = {},
  onEnterRoom,
}: {
  rooms: RoomTile[];
  cameras: CameraTile[];
  activeRoom: string | null;
  roomHistory?: Record<string, number[]>;
  onEnterRoom: (roomId: string) => void;
}) {
  const onlineByRoom: Record<string, number> = {};
  for (const r of rooms) {
    onlineByRoom[r.id] = r.camera_ids.filter(
      (id) => !cameras.find((c) => c.id === id)?.error
    ).length;
  }

  // busiest first; rooms with an unknown count (null) sink to the bottom; stable
  // tiebreak by name so equal-occupancy rooms don't shuffle between polls.
  const ordered = [...rooms].sort((a, b) => {
    const pa = a.persons ?? -1;
    const pb = b.persons ?? -1;
    return pb - pa || a.name.localeCompare(b.name);
  });

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
      {ordered.map((r) => (
        <RoomCard
          key={r.id}
          room={r}
          icon={ICON[r.name] ?? "📍"}
          active={r.id === activeRoom}
          online={onlineByRoom[r.id] ?? 0}
          history={roomHistory[r.id]}
          onClick={() => onEnterRoom(r.id)}
        />
      ))}
    </div>
  );
}

function RoomCard({
  room,
  icon,
  active,
  online,
  history,
  onClick,
}: {
  room: RoomTile;
  icon: string;
  active: boolean;
  online: number;
  history?: number[];
  onClick: () => void;
}) {
  const p = room.persons;
  const heat = heatFor(p);
  const fill = p == null ? 0 : Math.min(p / DENSITY_CAP, 1);
  const trend = trendOf(history);

  const shell = `group relative flex min-h-[116px] flex-col justify-between overflow-hidden rounded-2xl border p-3 text-left backdrop-blur-md transition duration-200 ${
    active
      ? "border-accent/60 bg-accent/[0.07] shadow-glow"
      : "border-white/10 bg-white/[0.03] hover:-translate-y-0.5 hover:border-white/25 hover:bg-white/[0.06]"
  }`;

  return (
    <button onClick={onClick} className={shell}>
      {active && (
        <span className="pointer-events-none absolute inset-x-0 top-0 h-px animate-shimmer bg-gradient-to-r from-transparent via-accent to-transparent [background-size:200%_100%]" />
      )}

      {/* identity */}
      <div className="flex w-full items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/[0.04] text-lg">
            {icon}
          </span>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-slate-100">{room.name}</div>
            <CameraHealth total={room.n_cameras} online={online} />
          </div>
        </div>
        {active && <AiBadge />}
      </div>

      {/* occupancy */}
      <div className="flex items-baseline gap-1.5">
        <span className={`font-display text-2xl font-black leading-none tabular-nums ${heat.text}`}>
          {fmtPersons(p)}
        </span>
        <span className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
          people
        </span>
        <TrendChevron dir={trend} />
      </div>

      {/* density meter — full-bleed bottom edge */}
      <span className="pointer-events-none absolute inset-x-0 bottom-0 h-1 bg-white/[0.05]">
        <span
          className="block h-full rounded-r-full transition-all duration-500"
          style={{ width: `${fill * 100}%`, background: heat.dot }}
        />
      </span>
    </button>
  );
}

function AiBadge() {
  return (
    <span className="flex shrink-0 items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-ink">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink/70" />
      AI
    </span>
  );
}

// Camera coverage as small dots: filled = online, hollow = offline. Falls back to
// a count when a room has many cameras.
function CameraHealth({ total, online }: { total: number; online: number }) {
  if (total <= 0) {
    return <span className="text-[10px] text-slate-500">no cameras</span>;
  }
  if (total > 6) {
    return (
      <span className="text-[10px] text-slate-500">
        📷 {online}/{total} online
      </span>
    );
  }
  return (
    <span className="mt-0.5 flex items-center gap-1" title={`${online}/${total} cameras online`}>
      {Array.from({ length: total }).map((_, i) => (
        <span
          key={i}
          className={`h-1.5 w-1.5 rounded-full ${i < online ? "bg-accent" : "border border-slate-500"}`}
        />
      ))}
    </span>
  );
}

function TrendChevron({ dir }: { dir: -1 | 0 | 1 }) {
  if (dir === 0) return null;
  const up = dir > 0;
  return (
    <span
      className={`text-[11px] font-bold ${up ? "text-danger" : "text-accent"}`}
      title={up ? "filling up" : "emptying"}
    >
      {up ? "▲" : "▼"}
    </span>
  );
}

// Direction of the recent occupancy trend: latest reading vs a few samples back.
function trendOf(history?: number[]): -1 | 0 | 1 {
  if (!history || history.length < 3) return 0;
  const last = history[history.length - 1];
  const prev = history[Math.max(0, history.length - 4)];
  if (last > prev) return 1;
  if (last < prev) return -1;
  return 0;
}
