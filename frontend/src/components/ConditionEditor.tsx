import { useEffect, useRef, useState, type ReactNode } from "react";
import { postJSON, type Predicate } from "../api";

export default function ConditionEditor({ activeId, onAdded }: { activeId: string; onAdded: () => void }) {
  const [text, setText] = useState("");
  const [action, setAction] = useState("log");
  const [preview, setPreview] = useState<Predicate | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (timer.current) window.clearTimeout(timer.current);
    if (!text.trim()) {
      setPreview(null);
      return;
    }
    timer.current = window.setTimeout(async () => {
      try {
        setPreview(await postJSON<Predicate>("/conditions/preview", { text }));
      } catch {
        setPreview(null);
      }
    }, 400);
  }, [text]);

  const add = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      await postJSON("/conditions", { text, action: { type: action }, camera_id: activeId || null });
      setText("");
      setPreview(null);
      onAdded();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-edge bg-panel p-4">
      <h2 className="mb-2 text-sm font-semibold text-slate-200">Add a condition</h2>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={'e.g. "someone raises their hand" · "more than 5 people" · "cineva pare agitat"'}
        className="h-20 w-full resize-none rounded-lg border border-edge bg-ink p-2 text-sm outline-none focus:border-accent"
      />
      <div className="mt-2 flex items-center gap-2">
        <select
          value={action}
          onChange={(e) => setAction(e.target.value)}
          className="rounded-lg border border-edge bg-ink px-2 py-1.5 text-sm"
        >
          <option value="log">Log</option>
          <option value="ntfy">📱 ntfy phone</option>
          <option value="webhook">Webhook</option>
          <option value="relay">Relay</option>
        </select>
        <button
          onClick={add}
          disabled={busy || !text.trim()}
          className="ml-auto rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-ink disabled:opacity-40"
        >
          {busy ? "Adding…" : "Add"}
        </button>
      </div>

      {preview && (
        <div className="mt-3 rounded-lg border border-edge bg-ink p-2 text-xs">
          <div className="mb-1 text-slate-400">compiled predicate</div>
          <div className="flex flex-wrap gap-1.5">
            <Tag>{preview.type}</Tag>
            <Tag>via {preview.evaluator}</Tag>
            {Object.entries(preview.params || {}).map(([k, v]) => (
              <Tag key={k}>
                {k}: {String(v)}
              </Tag>
            ))}
            <Tag>conf ≥ {preview.min_confidence}</Tag>
            <Tag>×{preview.min_consecutive}</Tag>
          </div>
          {preview.visual_question && (
            <div className="mt-1 text-slate-400">VLM: {preview.visual_question.slice(0, 90)}…</div>
          )}
        </div>
      )}
    </div>
  );
}

function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="rounded bg-edge px-1.5 py-0.5 text-[11px] text-slate-200">{children}</span>
  );
}
