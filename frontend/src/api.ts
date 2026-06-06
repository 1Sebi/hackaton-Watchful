export const API =
  (import.meta.env.VITE_API_BASE as string) || "http://localhost:8000";
export const WS_BASE = API.replace(/^http/, "ws");

export async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(API + path);
  return r.json();
}
export async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(API + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}
export async function putJSON<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(API + path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}
export async function del(path: string): Promise<Response> {
  return fetch(API + path, { method: "DELETE" });
}

export interface Predicate {
  type: string;
  evaluator: string;
  params: Record<string, unknown>;
  visual_question?: string | null;
  min_confidence: number;
  min_consecutive: number;
  cooldown_seconds: number;
}
export interface Condition {
  id: number;
  text: string;
  predicate: Predicate;
  action: { type?: string; [k: string]: unknown };
  enabled: boolean;
}
export interface EventItem {
  id?: number;
  seq?: number;
  condition_id?: number;
  camera_id?: string;
  camera_name?: string;
  text?: string;
  reason?: string;
  confidence?: number;
  evaluator?: string;
  ts?: number;
  timestamp?: string;
  action?: string;
  action_taken?: string;
}
export interface CameraTile {
  id: string;
  name: string;
  room: string;
  active: boolean;
  fps: number;
  detect_fps: number;
  persons: number | null;
  motion: number;
  moving: boolean;
  error?: string | null;
}
export interface CamerasState {
  active: string;
  cameras: CameraTile[];
}
export interface AgentState {
  running: boolean;
  fps: number;
  persons: number;
  conditions: number;
  error?: string | null;
  last_event?: EventItem | null;
  active?: string;
  camera_name?: string;
  cameras?: CameraTile[];
}
export async function getCameras(): Promise<CamerasState> {
  return getJSON<CamerasState>("/cameras");
}
export async function activateCamera(id: string): Promise<CamerasState> {
  return postJSON<CamerasState>(`/cameras/${id}/activate`, {});
}

export interface RoomTile {
  id: string;
  name: string;
  camera_ids: string[];
  n_cameras: number;
  persons: number | null;
  active: boolean;
}
export interface RoomsState {
  active_room: string | null;
  rooms: RoomTile[];
}
export async function getRooms(): Promise<RoomsState> {
  return getJSON<RoomsState>("/rooms");
}
export async function activateRoom(id: string, primaryCam?: string): Promise<RoomsState> {
  return postJSON<RoomsState>(`/rooms/${id}/activate`, {
    primary_cam: primaryCam ?? null,
  });
}
export interface Zone {
  id: number;
  name: string;
  polygon: number[][];
}
