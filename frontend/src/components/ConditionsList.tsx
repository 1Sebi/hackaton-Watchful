import { useEffect, useState } from "react";
import { type Condition, del, getJSON, putJSON } from "../api";

export default function ConditionsList({ activeId, refresh }: { activeId: string; refresh: number }) {
  const [items, setItems] = useState<Condition[]>([]);

  const load = async () =>
    setItems(await getJSON<Condition[]>(activeId ? `/conditions?camera_id=${activeId}` : "/conditions"));
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh, activeId]);

  const toggle = async (c: Condition) => {
    await putJSON(`/conditions/${c.id}`, { text: c.text, action: c.action, enabled: !c.enabled });
    load();
  };
  const remove = async (c: Condition) => {
    await del(`/conditions/${c.id}`);
    load();
  };

  return (
    <div className="rounded-xl border border-edge bg-panel p-4">
      <h2 className="mb-2 text-sm font-semibold text-slate-200">Conditions ({items.length})</h2>
      <div className="space-y-2">
        {items.length === 0 && <p className="text-xs text-slate-500">No conditions yet.</p>}
        {items.map((c) => (
          <div key={c.id} className="flex items-center gap-2 rounded-lg border border-edge bg-ink p-2">
            <button
              onClick={() => toggle(c)}
              title={c.enabled ? "enabled — click to pause" : "paused — click to enable"}
              className={`h-2.5 w-2.5 shrink-0 rounded-full ${c.enabled ? "bg-accent" : "bg-slate-600"}`}
            />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm text-slate-100">{c.text}</div>
              <div className="text-[11px] text-slate-400">
                {c.predicate?.type} · {c.predicate?.evaluator} · {c.action?.type}
              </div>
            </div>
            <button
              onClick={() => remove(c)}
              className="shrink-0 text-slate-500 hover:text-red-400"
              title="delete"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
