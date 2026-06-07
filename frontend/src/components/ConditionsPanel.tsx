import { useEffect, useMemo, useRef, useState } from "react";
import {
  createCondition,
  del,
  getCapabilities,
  listConditions,
  previewCondition,
  putJSON,
  type ActionCapability,
  type CameraTile,
  type Condition,
  type EventItem,
  type PredicatePreview,
} from "../api";

// Self-contained rule manager: write a condition in plain language, see exactly
// what it compiles to (with a reliability badge + warnings) and where the action
// will go BEFORE saving — then list / pause / delete existing rules. This is the
// "make it doable" surface: the preview + action check stop you from saving a rule
// that quietly does nothing.

const EXAMPLES = [
  "more than 10 people",
  "a person enters the jacuzzi",
  "no one in the room for 10 minutes",
  "someone raises their hand",
  "the room gets crowded",
];

type ActionState = Record<string, string | number>;

export default function ConditionsPanel({
  cameras,
  events = [],
}: {
  cameras: CameraTile[];
  events?: EventItem[];
}) {
  const [items, setItems] = useState<Condition[]>([]);
  const [caps, setCaps] = useState<ActionCapability[]>([]);
  const [text, setText] = useState("");
  const [cameraId, setCameraId] = useState<string>(""); // "" = all cameras (global)
  const [actionType, setActionType] = useState("telegram");
  const [actionCfg, setActionCfg] = useState<ActionState>({});
  const [count, setCount] = useState<number | "">(""); // people-threshold override
  const [preview, setPreview] = useState<PredicatePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const load = async () => setItems(await listConditions());
  useEffect(() => {
    load();
    getCapabilities().then(setCaps).catch(() => undefined);
  }, []);

  // only Telegram + Relay are offered as actions
  const shownCaps = useMemo(
    () => caps.filter((c) => c.type === "telegram" || c.type === "relay"),
    [caps],
  );
  const cap = useMemo(() => caps.find((c) => c.type === actionType), [caps, actionType]);

  // does this rule have a people threshold the user can tune? (COUNT_GT/LT/EQ)
  const countType = preview && ["COUNT_GT", "COUNT_LT", "COUNT_EQ"].includes(preview.type);
  const countCmp = preview?.type === "COUNT_LT" ? "fewer than" : preview?.type === "COUNT_EQ" ? "exactly" : "more than";
  const thr = count !== "" ? count : (preview?.params?.value as number | undefined) ?? "";

  // seed the threshold box from the parsed number once we know it's a count rule
  useEffect(() => {
    if (countType && count === "" && preview?.params?.value != null) {
      setCount(Number(preview.params.value));
    }
  }, [countType, count, preview]);

  // assemble the action dict the backend expects from the selected type + fields
  const builtAction = useMemo(() => {
    const a: Record<string, unknown> = { type: actionType };
    for (const f of cap?.fields ?? []) {
      if (f.when) {
        const ok = Object.entries(f.when).every(([k, v]) => String(actionCfg[k] ?? "") === v);
        if (!ok) continue;
      }
      const raw = actionCfg[f.key] ?? f.default;
      a[f.key] = f.type === "number" ? Number(raw) : raw;
    }
    return a;
  }, [actionType, actionCfg, cap]);

  // live preview (debounced) whenever the text or action changes
  useEffect(() => {
    if (timer.current) window.clearTimeout(timer.current);
    if (!text.trim()) {
      setPreview(null);
      return;
    }
    timer.current = window.setTimeout(async () => {
      try {
        setPreview(await previewCondition(text, builtAction, count === "" ? null : count));
      } catch {
        setPreview(null);
      }
    }, 350);
  }, [text, builtAction, count]);

  const blocked = preview?.action_check && preview.action_check.ok === false;

  const add = async () => {
    if (!text.trim() || blocked) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await createCondition({
        text,
        action: builtAction,
        camera_id: cameraId || null,
        count: count === "" ? null : count,
      });
      if ((res as { detail?: string }).detail) {
        setErr((res as { detail?: string }).detail!);
        return;
      }
      setText("");
      setPreview(null);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (c: Condition) => {
    await putJSON(`/conditions/${c.id}`, { text: c.text, action: c.action, enabled: !c.enabled });
    load();
  };
  const remove = async (c: Condition) => {
    await del(`/conditions/${c.id}`);
    load();
  };

  const camName = (id?: string | null) =>
    !id ? "All cameras" : cameras.find((c) => c.id === id)?.name ?? id;

  // map condition_id -> rule text so firings read "a person enters the jacuzzi"
  // instead of the cryptic "condition #3"
  const ruleText = useMemo(() => {
    const m = new Map<number, string>();
    items.forEach((c) => m.set(c.id, c.text));
    return m;
  }, [items]);

  // collapse consecutive firings of the same rule (the jacuzzi relay re-fires every
  // cooldown) into one row with a ×N count, so the feed isn't spammy
  const recent = useMemo(() => {
    const out: {
      condition_id?: number;
      camera_id?: string;
      reason?: string;
      action?: string;
      ts?: number;
      timestamp?: string;
      count: number;
    }[] = [];
    for (const e of events) {
      const action = (e.action || e.action_taken) as string | undefined;
      const last = out[out.length - 1];
      if (last && last.condition_id === e.condition_id && last.action === action) {
        last.count++;
      } else {
        out.push({
          condition_id: e.condition_id,
          camera_id: e.camera_id,
          reason: e.reason,
          action,
          ts: e.ts,
          timestamp: e.timestamp,
          count: 1,
        });
      }
    }
    return out.slice(0, 6);
  }, [events]);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
      {/* ── builder ── */}
      <div>
        <textarea
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setCount(""); // let the new text re-seed the threshold
          }}
          placeholder={'Describe it in plain words — e.g. "more than 10 people in the lobby"'}
          className="h-20 w-full resize-none rounded-xl border border-white/10 bg-white/[0.04] p-3 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-accent/60"
        />
        <div className="mt-2 flex flex-wrap gap-1.5">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => setText(ex)}
              className="chip glass-hover cursor-pointer"
              type="button"
            >
              {ex}
            </button>
          ))}
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2">
          <Field label="Where">
            <select
              value={cameraId}
              onChange={(e) => setCameraId(e.target.value)}
              className="select"
            >
              <option value="">All cameras</option>
              {cameras.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.room ? `${c.room} · ${c.name}` : c.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Do this">
            <select
              value={actionType}
              onChange={(e) => {
                setActionType(e.target.value);
                setActionCfg({});
              }}
              className="select"
            >
              {shownCaps.map((a) => (
                <option key={a.type} value={a.type}>
                  {a.label}
                  {a.configured ? "" : " — needs setup"}
                </option>
              ))}
            </select>
          </Field>
        </div>

        {/* people threshold — only for count rules; tune N directly */}
        {countType && (
          <div className="mt-2">
            <Field label="How many people">
              <div className="flex items-center gap-2">
                <span className="shrink-0 text-sm text-slate-400">{countCmp}</span>
                <input
                  type="number"
                  min={0}
                  value={String(thr)}
                  onChange={(e) =>
                    setCount(e.target.value === "" ? "" : Math.max(0, Number(e.target.value)))
                  }
                  className="select w-20 text-center"
                />
                <span className="shrink-0 text-sm text-slate-400">people</span>
              </div>
            </Field>
          </div>
        )}

        {/* per-action config fields (relay port/mode, webhook url, …) */}
        {(cap?.fields ?? []).map((f) => {
          if (f.when) {
            const show = Object.entries(f.when).every(
              ([k, v]) => String(actionCfg[k] ?? "") === v,
            );
            if (!show) return null;
          }
          const val = actionCfg[f.key] ?? (f.default as string | number);
          return (
            <div className="mt-2" key={f.key}>
              <Field label={f.label}>
                {f.type === "select" ? (
                  <select
                    value={String(val)}
                    onChange={(e) => setActionCfg((s) => ({ ...s, [f.key]: e.target.value }))}
                    className="select"
                  >
                    {f.options?.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type={f.type}
                    value={String(val)}
                    onChange={(e) => setActionCfg((s) => ({ ...s, [f.key]: e.target.value }))}
                    className="select"
                  />
                )}
              </Field>
            </div>
          );
        })}

        {cap && !cap.configured && (
          <p className="mt-2 text-[11px] text-amber">⚠ {cap.hint}</p>
        )}

        {/* live preview — plain words only, no jargon */}
        {preview && (
          <div className="mt-3 rounded-xl border border-white/10 bg-white/[0.03] p-3">
            <div className="flex items-start gap-2">
              <ReliabilityBadge r={preview.explain.reliability} />
              <span className="text-sm text-slate-100">{preview.explain.summary}</span>
            </div>
            {preview.explain.warnings.map((w, i) => (
              <p key={i} className="mt-2 text-[11px] text-amber">
                ⚠ {w}
              </p>
            ))}
            {preview.action_check?.error && (
              <p className="mt-2 text-[11px] text-red-400">✕ {preview.action_check.error}</p>
            )}
            {preview.action_check?.warnings.map((w, i) => (
              <p key={i} className="mt-2 text-[11px] text-amber">
                ⚠ {w}
              </p>
            ))}
          </div>
        )}

        {err && <p className="mt-2 text-[11px] text-red-400">✕ {err}</p>}

        <button
          onClick={add}
          disabled={busy || !text.trim() || !!blocked}
          className="mt-3 w-full rounded-xl bg-accent px-4 py-2 text-sm font-bold text-ink shadow-glow transition hover:bg-accent/90 disabled:opacity-40 disabled:shadow-none"
        >
          {busy ? "Adding…" : blocked ? "Fix the action first" : "Add rule"}
        </button>
      </div>

      {/* ── existing rules ── */}
      <div>
        <div className="mb-2 label-eyebrow">Active rules ({items.length})</div>
        <div className="space-y-2">
          {items.length === 0 && (
            <p className="rounded-xl border border-dashed border-white/10 p-4 text-center text-xs text-slate-500">
              No rules yet. Describe what the agent should watch for on the left.
            </p>
          )}
          {items.map((c) => (
            <div
              key={c.id}
              className="flex items-start gap-2.5 rounded-xl border border-white/10 bg-white/[0.03] p-2.5"
            >
              <button
                onClick={() => toggle(c)}
                title={c.enabled ? "enabled — click to pause" : "paused — click to enable"}
                className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${
                  c.enabled ? "bg-accent shadow-glow" : "bg-slate-600"
                }`}
              />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-slate-100">{c.text}</div>
                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-400">
                  <span className="chip">→ {actionLabel(c.action)}</span>
                  <span className="text-slate-500">on {camName(c.camera_id)}</span>
                </div>
              </div>
              <button
                onClick={() => remove(c)}
                className="shrink-0 text-slate-500 transition hover:text-red-400"
                title="delete rule"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      </div>
      </div>

      {/* recently fired — collapsed runs, shows the rule text not "condition #N" */}
      {recent.length > 0 && (
        <div>
          <div className="mb-2 label-eyebrow">Recently fired</div>
          <div className="grid gap-2 sm:grid-cols-2">
            {recent.map((e, i) => (
              <div
                key={i}
                className="flex items-center gap-2.5 rounded-xl border border-white/10 bg-white/[0.03] p-2.5"
              >
                <span className="h-2 w-2 shrink-0 rounded-full bg-iris" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-slate-100">
                    {(e.condition_id != null && ruleText.get(e.condition_id)) ||
                      `condition #${e.condition_id ?? "?"}`}
                    {e.count > 1 && (
                      <span className="ml-1 text-[11px] text-slate-500">×{e.count}</span>
                    )}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-400">
                    <span className="text-slate-500">📷 {camName(e.camera_id)}</span>
                    {e.reason && <span className="truncate">{e.reason}</span>}
                    {e.action && <span className="text-iris">→ {e.action}</span>}
                  </div>
                </div>
                <span className="shrink-0 text-[10px] tabular-nums text-slate-500">
                  {fmtTime(e)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function fmtTime(e: { ts?: number; timestamp?: string }): string {
  const t = e.ts ? new Date(e.ts * 1000) : e.timestamp ? new Date(e.timestamp) : null;
  return t ? t.toLocaleTimeString() : "";
}

function ReliabilityBadge({ r }: { r: "precise" | "visual" }) {
  return r === "precise" ? (
    <span className="mt-0.5 shrink-0 chip border-accent/30 bg-accent/10 text-accent">✓ reliable</span>
  ) : (
    <span className="mt-0.5 shrink-0 chip border-amber/30 bg-amber/10 text-amber">~ AI guess</span>
  );
}

// plain, icon-led action labels — no "relay_off" / "telegram" jargon for newcomers
function actionLabel(a: Condition["action"]): string {
  const t = ((a?.type as string) || "log").toLowerCase();
  if (t === "telegram") return "✈ Telegram";
  if (t === "whatsapp") return "WhatsApp";
  if (t === "ntfy") return "Phone alert";
  if (t === "relay" || t === "relay_on" || t === "relay_off") {
    const port = a?.port ?? 1;
    const state = a?.state === "low" || t === "relay_off" ? "off" : a?.duration ? `${a.duration}s` : "on";
    return `Relay ${port} ${state}`;
  }
  if (t === "log") return "Just log it";
  return t;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        {label}
      </span>
      {children}
    </label>
  );
}
