import { useCountUp } from "../../hooks/useCountUp";
import Sparkline from "./Sparkline";

// A KPI tile for the command-center bento row: big animated number, label,
// icon, optional unit + trend sparkline + accent tint.
export default function StatCard({
  label,
  value,
  unit,
  icon,
  history,
  color = "#22d3a8",
  decimals = 0,
  delay = 0,
}: {
  label: string;
  value: number;
  unit?: string;
  icon: string;
  history?: number[];
  color?: string;
  decimals?: number;
  delay?: number;
}) {
  const animated = useCountUp(value);
  const shown = decimals ? animated.toFixed(decimals) : Math.round(animated).toString();
  return (
    <div
      className="glass glass-hover animate-fade-up relative overflow-hidden p-4"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div
        className="pointer-events-none absolute -right-6 -top-8 h-24 w-24 rounded-full opacity-[0.18] blur-2xl"
        style={{ background: color }}
      />
      <div className="flex items-center justify-between">
        <span className="label-eyebrow">{label}</span>
        <span className="text-base" aria-hidden>
          {icon}
        </span>
      </div>
      <div className="mt-2 flex items-end gap-1">
        <span className="stat-num" style={{ color }}>
          {shown}
        </span>
        {unit && <span className="mb-0.5 text-xs font-medium text-slate-400">{unit}</span>}
      </div>
      {history && history.length > 1 && (
        <div className="mt-2 -mb-1">
          <Sparkline data={history} color={color} width={150} height={28} />
        </div>
      )}
    </div>
  );
}
