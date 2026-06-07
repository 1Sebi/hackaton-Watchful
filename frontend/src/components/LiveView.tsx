import { useEffect, useRef, useState } from "react";
import {
  API,
  getDetections,
  pinTrack,
  stopPin,
  type DetectionsState,
  type PinStopResult,
  type TrackBox,
} from "../api";

type AnimBox = { id: number; bbox: [number, number, number, number]; dur: number };

// Big focused feed for the active camera. Glass frame + LIVE chip + a clickable
// detection overlay: poll /track/detections, draw a box per person on top of the
// MJPEG, click one to PIN + record their path, then "Stop & send" pushes the clip
// to Telegram. Boxes are mapped from frame-pixel space to the rendered <img> using
// the object-cover transform so clicks land on the right person.
export default function LiveView({
  activeId,
  label,
}: {
  activeId: string;
  label?: string;
}) {
  const src = activeId ? `/stream/${activeId}/live.mjpg` : "/stream/live.mjpg";
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [dets, setDets] = useState<DetectionsState | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [, forceTick] = useState(0); // re-render to recompute box geometry

  // latest detection targets (updated ~4/s) and the smoothly-animated boxes that
  // chase them at 60fps, so boxes glide instead of jumping at the detect rate.
  const targetsRef = useRef<Map<number, TrackBox>>(new Map());
  const [animBoxes, setAnimBoxes] = useState<AnimBox[]>([]);

  const pinnedId = dets?.pinned_id ?? null;

  // poll the detection boxes (and pin state) a few times a second
  useEffect(() => {
    if (!activeId) return;
    let stop = false;
    const tick = async () => {
      try {
        const d = await getDetections(activeId);
        if (stop) return;
        setDets(d);
        targetsRef.current = new Map(d.tracks.map((t) => [t.id, t]));
      } catch {
        /* keep last */
      }
    };
    tick();
    const h = window.setInterval(tick, 250);
    const onResize = () => forceTick((n) => n + 1);
    window.addEventListener("resize", onResize);
    return () => {
      stop = true;
      window.clearInterval(h);
      window.removeEventListener("resize", onResize);
    };
  }, [activeId]);

  // 60fps interpolation loop — each frame eases every box toward its target; new
  // ids snap in, vanished ids drop out. Cheap (a handful of boxes) and buttery.
  useEffect(() => {
    let raf = 0;
    const lerp = (a: number, b: number) => a + (b - a) * 0.3;
    const step = () => {
      const targets = targetsRef.current;
      setAnimBoxes((prev) => {
        const prevById = new Map(prev.map((b) => [b.id, b]));
        const out: AnimBox[] = [];
        targets.forEach((t, id) => {
          const p = prevById.get(id);
          const cur = p ? p.bbox : t.bbox;
          out.push({
            id,
            dur: t.dur,
            bbox: [
              lerp(cur[0], t.bbox[0]),
              lerp(cur[1], t.bbox[1]),
              lerp(cur[2], t.bbox[2]),
              lerp(cur[3], t.bbox[3]),
            ],
          });
        });
        return out;
      });
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, []);

  // reset transient UI on camera switch
  useEffect(() => {
    setDets(null);
    setToast(null);
    targetsRef.current = new Map();
    setAnimBoxes([]);
  }, [activeId]);

  const pin = async (id: number) => {
    try {
      await pinTrack(activeId, id);
      setToast(`Pinned #${id} — recording path…`);
      const d = await getDetections(activeId);
      setDets(d);
    } catch {
      setToast("Could not pin");
    }
  };

  const stop = async () => {
    setBusy(true);
    setToast("Finalizing clip & sending to Telegram…");
    try {
      const r: PinStopResult = await stopPin();
      if (r.ok) {
        const n = r.telegram?.sent ?? 0;
        setToast(`✅ Sent clip (${r.duration ?? "?"}s) to ${n} Telegram chat${n === 1 ? "" : "s"}`);
      } else {
        setToast(`✕ ${r.error || r.telegram?.error || "send failed"}`);
      }
      setDets(await getDetections(activeId));
    } catch {
      setToast("✕ stop failed");
    } finally {
      setBusy(false);
    }
  };

  // map a frame-pixel rect to on-screen px using the object-cover transform
  const boxStyle = (b: [number, number, number, number]): React.CSSProperties | null => {
    const img = imgRef.current;
    if (!img || !img.naturalWidth) return null;
    const NW = img.naturalWidth;
    const NH = img.naturalHeight;
    const CW = img.clientWidth;
    const CH = img.clientHeight;
    const scale = Math.max(CW / NW, CH / NH); // object-cover
    const offX = (CW - NW * scale) / 2;
    const offY = (CH - NH * scale) / 2;
    const [x1, y1, x2, y2] = b;
    return {
      left: offX + x1 * scale,
      top: offY + y1 * scale,
      width: (x2 - x1) * scale,
      height: (y2 - y1) * scale,
    };
  };

  return (
    <div className="glass relative overflow-hidden p-0">
      <div className="feed-skeleton relative aspect-video w-full">
        <img
          key={activeId}
          ref={imgRef}
          src={API + src}
          alt="live camera feed with detection overlays"
          className="block aspect-video w-full object-cover"
          onLoad={() => forceTick((n) => n + 1)}
          onError={(e) => ((e.target as HTMLImageElement).style.opacity = "0.25")}
        />

        {/* clickable detection boxes (60fps-interpolated) */}
        <div className="absolute inset-0">
          {animBoxes.map((t) => {
            const st = boxStyle(t.bbox);
            if (!st) return null;
            const isPinned = t.id === pinnedId;
            return (
              <button
                key={t.id}
                onClick={() => pin(t.id)}
                title={`Pin person #${t.id} (${t.dur}s)`}
                style={st}
                className={`absolute rounded-md border-2 transition ${
                  isPinned
                    ? "border-orange-400 bg-orange-400/15 shadow-[0_0_0_2px_rgba(251,146,60,0.4)]"
                    : "border-accent/70 hover:border-accent hover:bg-accent/10"
                }`}
              >
                <span
                  className={`absolute -top-5 left-0 whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                    isPinned ? "bg-orange-400 text-black" : "bg-accent/80 text-black"
                  }`}
                >
                  {isPinned ? `📌 #${t.id}` : `#${t.id}`}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* LIVE + label chips */}
      <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-2">
        <span className="flex items-center gap-1.5 rounded-full bg-black/55 px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-accent backdrop-blur">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" /> live
        </span>
        {label && (
          <span className="rounded-full bg-black/55 px-2.5 py-1 text-[11px] font-medium text-white backdrop-blur">
            {label}
          </span>
        )}
        {pinnedId != null && (
          <span className="flex items-center gap-1.5 rounded-full bg-black/55 px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-orange-400 backdrop-blur">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" /> rec #{pinnedId}
          </span>
        )}
      </div>

      {/* pin controls / hint */}
      <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between gap-2">
        <span className="rounded-full bg-black/55 px-2.5 py-1 text-[11px] text-slate-200 backdrop-blur">
          {pinnedId != null
            ? "Recording this person's path"
            : "Click a person to pin & record their path"}
        </span>
        {pinnedId != null && (
          <button
            onClick={stop}
            disabled={busy}
            className="rounded-full bg-orange-500 px-3 py-1.5 text-[12px] font-bold text-black transition hover:brightness-110 disabled:opacity-50"
          >
            {busy ? "Sending…" : "■ Stop & send"}
          </button>
        )}
      </div>

      {toast && (
        <div className="absolute left-1/2 top-3 -translate-x-1/2 rounded-lg bg-black/75 px-3 py-1.5 text-[12px] text-white backdrop-blur">
          {toast}
        </div>
      )}

      <div className="pointer-events-none absolute inset-0 rounded-2xl ring-1 ring-inset ring-white/10" />
    </div>
  );
}
