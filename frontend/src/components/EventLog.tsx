import GlassCard from "./ui/GlassCard";
import EventFeed from "./EventFeed";
import { useEvents } from "../hooks/useVenueData";

// Standalone event log card (kept for any view that wants the feed on its own).
// The shared presentational list lives in EventFeed; data comes from useEvents.
export default function EventLog() {
  const events = useEvents();
  return (
    <GlassCard eyebrow="Event log">
      <EventFeed events={events} max={20} />
    </GlassCard>
  );
}
