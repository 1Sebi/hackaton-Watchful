import { useEffect, useRef, useState, type MouseEvent } from "react";
import { API, del, getJSON, postJSON, type Zone } from "../api";

function snapUrl(activeId: string): string {
  const path = activeId ? `/stream/${activeId}/snapshot.jpg` : "/stream/snapshot.jpg";
  return API + path + "?ts=" + Date.now();
}

export default function ZoneDrawer({ activeId }: { activeId: string }) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [points, setPoints] = useState<[number, number][]>([]);
  const [name, setName] = useState("");
  const [zones, setZones] = useState<Zone[]>([]);
  const [snap, setSnap] = useState(snapUrl(activeId));

  const load = async () =>
    setZones(await getJSON<Zone[]>(activeId ? `/zones?camera_id=${activeId}` : "/zones"));
  useEffect(() => {
    setSnap(snapUrl(activeId)); // fresh snapshot for the newly active camera
    setPoints([]);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  const click = (e: MouseEvent<HTMLDivElement>) => {
    const img = imgRef.current;
    if (!img) return;
    const rect = img.getBoundingClientRect();
    const nx = (e.clientX - rect.left) / rect.width;
    const ny = (e.clientY - rect.top) / rect.height;
    const x = Math.round(nx * (img.naturalWidth || 640));
    const y = Math.round(ny * (img.naturalHeight || 480));
    setPoints((p) => [...p, [x, y]]);
  };

  const save = async () => {
    if (points.length < 3 || !name.trim()) return;
    await postJSON("/zones", { name, polygon: points, camera_id: activeId || null });
    setPoints([]);
    setName("");
    load();
  };
  const removeZone = async (z: Zone) => {
    await del(`/zones/${z.id}`);
    load();
  };

  return (
    <div className="rounded-xl border border-edge bg-panel p-4">
      <h2 className="mb-2 text-sm font-semibold text-slate-200">Zones — click to draw a polygon</h2>
      <div className="relative inline-block cursor-crosshair select-none" onClick={click}>
        <img ref={imgRef} src={snap} className="block w-full rounded-lg border border-edge" alt="snapshot" />
        <svg className="pointer-events-none absolute inset-0 h-full w-full">
          {points.length > 0 && (
            <polygon
              points={points.map(([x, y]) => svgPt(imgRef.current, x, y)).join(" ")}
              fill="rgba(34,211,168,0.25)"
              stroke="#22d3a8"
              strokeWidth={2}
            />
          )}
          {points.map(([x, y], i) => {
            const [sx, sy] = svgPt(imgRef.current, x, y).split(",").map(Number);
            return <circle key={i} cx={sx} cy={sy} r={3} fill="#22d3a8" />;
          })}
        </svg>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="zone name (e.g. jacuzzi)"
          className="min-w-0 flex-1 rounded-lg border border-edge bg-ink px-2 py-1.5 text-sm"
        />
        <button onClick={() => setPoints([])} className="rounded-lg border border-edge px-3 py-1.5 text-sm">
          Clear
        </button>
        <button
          onClick={() => setSnap(snapUrl(activeId))}
          className="rounded-lg border border-edge px-3 py-1.5 text-sm"
          title="refresh snapshot"
        >
          ↻
        </button>
        <button
          onClick={save}
          disabled={points.length < 3 || !name.trim()}
          className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-40"
        >
          Save zone
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {zones.map((z) => (
          <span key={z.id} className="flex items-center gap-1 rounded bg-edge px-2 py-0.5 text-xs">
            {z.name}
            <button onClick={() => removeZone(z)} className="text-slate-500 hover:text-red-400">
              ✕
            </button>
          </span>
        ))}
      </div>
    </div>
  );
}

function svgPt(img: HTMLImageElement | null, x: number, y: number): string {
  if (!img) return `${x},${y}`;
  const sx = img.clientWidth / (img.naturalWidth || 640);
  const sy = img.clientHeight / (img.naturalHeight || 480);
  return `${x * sx},${y * sy}`;
}
