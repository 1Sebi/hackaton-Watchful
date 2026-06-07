// Pulsing live/offline indicator. The dot animates a ping ring when live.
export default function LivePill({ live, label }: { live: boolean; label?: string }) {
  return (
    <span className="chip">
      <span className="relative flex h-2 w-2">
        {live && (
          <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full" />
        )}
        <span
          className={`inline-flex h-2 w-2 rounded-full ${live ? "bg-accent" : "bg-danger"}`}
        />
      </span>
      <span className={live ? "text-accent" : "text-danger"}>
        {label ?? (live ? "LIVE" : "OFFLINE")}
      </span>
    </span>
  );
}
