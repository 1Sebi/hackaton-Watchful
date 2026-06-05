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
  text?: string;
  reason?: string;
  confidence?: number;
  evaluator?: string;
  ts?: number;
  timestamp?: string;
  action?: string;
  action_taken?: string;
}
export interface AgentState {
  running: boolean;
  fps: number;
  persons: number;
  conditions: number;
  error?: string | null;
  last_event?: EventItem | null;
}
export interface Zone {
  id: number;
  name: string;
  polygon: number[][];
}
