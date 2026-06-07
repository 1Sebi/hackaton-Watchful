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
  camera_id?: string | null;
}

// plain-language explanation of a compiled predicate (from /conditions/preview)
export interface PredicateExplain {
  summary: string;
  reliability: "precise" | "visual";
  reliable: boolean;
  warnings: string[];
}
export interface ActionCheck {
  ok: boolean;
  error: string | null;
  warnings: string[];
}
export interface PredicatePreview extends Predicate {
  explain: PredicateExplain;
  action_check?: ActionCheck;
}
export interface ActionField {
  key: string;
  label: string;
  type: "number" | "text" | "select";
  default: unknown;
  options?: { value: string; label: string }[];
  when?: Record<string, string>;
}
export interface ActionCapability {
  type: string;
  label: string;
  configured: boolean;
  always?: boolean;
  hint: string;
  fields: ActionField[];
}

export async function getCapabilities(): Promise<ActionCapability[]> {
  return (await getJSON<{ actions: ActionCapability[] }>("/conditions/capabilities")).actions;
}
export async function previewCondition(
  text: string,
  action?: unknown,
  count?: number | null,
): Promise<PredicatePreview> {
  return postJSON<PredicatePreview>("/conditions/preview", { text, action, count });
}
export async function listConditions(cameraId?: string | null): Promise<Condition[]> {
  return getJSON<Condition[]>(cameraId ? `/conditions?camera_id=${cameraId}` : "/conditions");
}
export async function createCondition(body: {
  text: string;
  action: unknown;
  camera_id?: string | null;
  enabled?: boolean;
  count?: number | null;
}): Promise<Condition & { warnings?: string[]; detail?: string }> {
  const r = await fetch(API + "/conditions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
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

// ── person pin-tracking ──────────────────────────────────────────────
export interface TrackBox {
  id: number;
  bbox: [number, number, number, number]; // x1,y1,x2,y2 in frame pixels
  center: [number, number];
  dur: number;
}
export interface DetectionsState {
  camera_id: string | null;
  frame_w: number;
  frame_h: number;
  pinned_id: number | null;
  tracks: TrackBox[];
}
export interface PinStatus {
  pinned: boolean;
  camera_id?: string;
  camera_name?: string;
  track_id?: number;
  frames?: number;
  duration?: number;
}
export interface PinStopResult {
  ok: boolean;
  error?: string;
  frames?: number;
  duration?: number;
  track_id?: number;
  camera_name?: string;
  telegram?: { ok: boolean; sent?: number; recipients?: number; error?: string };
}
export async function getDetections(cameraId?: string): Promise<DetectionsState> {
  return getJSON<DetectionsState>(`/track/detections${cameraId ? `?camera_id=${cameraId}` : ""}`);
}
export async function pinTrack(cameraId: string, trackId: number): Promise<PinStatus> {
  return postJSON<PinStatus>("/track/pin", { camera_id: cameraId, track_id: trackId });
}
export async function stopPin(): Promise<PinStopResult> {
  return postJSON<PinStopResult>("/track/stop", {});
}
