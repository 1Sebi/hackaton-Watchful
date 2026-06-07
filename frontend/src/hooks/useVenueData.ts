import { useEffect, useRef, useState } from "react";
import {
  getCameras,
  getJSON,
  WS_BASE,
  type AgentState,
  type CameraTile,
  type EventItem,
  type RoomsState,
  type RoomTile,
} from "../api";

const HISTORY_LEN = 40;

export interface VenueData {
  rooms: RoomTile[];
  cameras: CameraTile[];
  activeRoom: string | null;
  // aggregates
  totalPersons: number;
  roomsCount: number;
  camsOnline: number;
  camsTotal: number;
  busiest: RoomTile[];
  // rolling trend buffers for sparklines
  personsHistory: number[];
  roomHistory: Record<string, number[]>; // per-room occupancy trend
  loaded: boolean;
}

// Polls /rooms + /cameras together, derives venue-wide aggregates, and keeps a
// short rolling history of total occupancy for the KPI sparklines. One hook so
// every dashboard widget shares a single polling cadence.
export function useVenueData(intervalMs = 3000): VenueData {
  const [rooms, setRooms] = useState<RoomTile[]>([]);
  const [cameras, setCameras] = useState<CameraTile[]>([]);
  const [activeRoom, setActiveRoom] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const histRef = useRef<number[]>([]);
  const roomHistRef = useRef<Record<string, number[]>>({});
  const [personsHistory, setPersonsHistory] = useState<number[]>([]);
  const [roomHistory, setRoomHistory] = useState<Record<string, number[]>>({});

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const [rs, cs] = await Promise.all([getJSON<RoomsState>("/rooms"), getCameras()]);
        if (stop) return;
        setRooms(rs.rooms);
        setActiveRoom(rs.active_room);
        setCameras(cs.cameras);
        const total = rs.rooms.reduce((s, r) => s + (r.persons ?? 0), 0);
        histRef.current = [...histRef.current, total].slice(-HISTORY_LEN);
        setPersonsHistory(histRef.current);
        // per-room trend buffers (only append once a count is known)
        const next: Record<string, number[]> = { ...roomHistRef.current };
        for (const r of rs.rooms) {
          if (r.persons == null) continue;
          next[r.id] = [...(next[r.id] ?? []), r.persons].slice(-HISTORY_LEN);
        }
        roomHistRef.current = next;
        setRoomHistory(next);
        setLoaded(true);
      } catch {
        /* keep last good state */
      }
    };
    tick();
    const h = window.setInterval(tick, intervalMs);
    return () => {
      stop = true;
      window.clearInterval(h);
    };
  }, [intervalMs]);

  const totalPersons = rooms.reduce((s, r) => s + (r.persons ?? 0), 0);
  const camsTotal = cameras.length;
  const camsOnline = cameras.filter((c) => !c.error).length;
  const busiest = [...rooms]
    .filter((r) => (r.persons ?? 0) > 0)
    .sort((a, b) => (b.persons ?? 0) - (a.persons ?? 0))
    .slice(0, 5);

  return {
    rooms,
    cameras,
    activeRoom,
    totalPersons,
    roomsCount: rooms.length,
    camsOnline,
    camsTotal,
    busiest,
    personsHistory,
    roomHistory,
    loaded,
  };
}

// Live agent state over WS (running flag + FPS), with auto-reconnect.
export function useAgentState(): AgentState | null {
  const [state, setState] = useState<AgentState | null>(null);
  const fpsHistRef = useRef<number[]>([]);
  useEffect(() => {
    let ws: WebSocket;
    let stop = false;
    const connect = () => {
      ws = new WebSocket(WS_BASE + "/ws/state");
      ws.onmessage = (e) => {
        try {
          setState(JSON.parse(e.data));
        } catch {
          /* ignore malformed frame */
        }
      };
      ws.onclose = () => {
        if (!stop) setTimeout(connect, 1500);
      };
      ws.onerror = () => ws.close();
    };
    connect();
    return () => {
      stop = true;
      ws?.close();
    };
  }, []);
  void fpsHistRef;
  return state;
}

// Live event feed over WS, seeded from the REST history. Optionally filtered to
// a single camera/room set.
export function useEvents(limit = 60): EventItem[] {
  const [events, setEvents] = useState<EventItem[]>([]);
  useEffect(() => {
    let stop = false;
    getJSON<EventItem[]>("/events")
      .then((e) => !stop && setEvents(e.slice(0, limit)))
      .catch(() => undefined);
    let ws: WebSocket;
    const connect = () => {
      ws = new WebSocket(WS_BASE + "/ws/events");
      ws.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data) as EventItem;
          setEvents((prev) => [ev, ...prev].slice(0, limit));
        } catch {
          /* ignore */
        }
      };
      ws.onclose = () => {
        if (!stop) setTimeout(connect, 1500);
      };
      ws.onerror = () => ws.close();
    };
    connect();
    return () => {
      stop = true;
      ws?.close();
    };
  }, [limit]);
  return events;
}
