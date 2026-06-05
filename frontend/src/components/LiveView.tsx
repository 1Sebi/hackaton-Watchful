import { API } from "../api";

export default function LiveView() {
  return (
    <div className="overflow-hidden rounded-xl border border-edge bg-black">
      <img
        src={API + "/stream/live.mjpg"}
        alt="live camera feed with overlays"
        className="block w-full"
        onError={(e) => ((e.target as HTMLImageElement).style.opacity = "0.25")}
      />
    </div>
  );
}
