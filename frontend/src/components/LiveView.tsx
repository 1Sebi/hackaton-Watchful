import { API } from "../api";

export default function LiveView({ activeId }: { activeId: string }) {
  // Stream the active camera explicitly so a camera switch remounts the <img>
  // (clean reconnect). Falls back to the server-side active alias before load.
  const src = activeId ? `/stream/${activeId}/live.mjpg` : "/stream/live.mjpg";
  return (
    <div className="overflow-hidden rounded-xl border border-edge bg-black">
      <img
        key={activeId}
        src={API + src}
        alt="live camera feed with overlays"
        className="block w-full"
        onError={(e) => ((e.target as HTMLImageElement).style.opacity = "0.25")}
      />
    </div>
  );
}
