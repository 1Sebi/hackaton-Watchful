// Shared occupancy → color/heat mapping so the map tiles, KPI pills, and room
// header all read the same scale. `null` = not yet reported.

export interface Heat {
  text: string; // tailwind text color class
  bg: string; // tailwind bg class
  ring: string; // tailwind ring/border tint
  dot: string; // hex for sparkline / svg
}

export function heatFor(persons: number | null): Heat {
  if (persons == null)
    return { text: "text-slate-500", bg: "bg-white/[0.03]", ring: "border-white/10", dot: "#64748b" };
  if (persons === 0)
    return { text: "text-slate-300", bg: "bg-white/[0.04]", ring: "border-white/10", dot: "#94a3b8" };
  if (persons >= 8)
    return { text: "text-danger", bg: "bg-danger/10", ring: "border-danger/40", dot: "#fb6a78" };
  if (persons >= 4)
    return { text: "text-amber", bg: "bg-amber/10", ring: "border-amber/40", dot: "#f5b343" };
  return { text: "text-accent", bg: "bg-accent/10", ring: "border-accent/40", dot: "#22d3a8" };
}

export function fmtPersons(p: number | null): string {
  return p == null ? "—" : String(p);
}
