import type { ReactNode } from "react";

// The core surface primitive. Frosted glass panel with optional eyebrow label,
// accent glow, and staggered mount animation.
export default function GlassCard({
  children,
  className = "",
  eyebrow,
  right,
  glow,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  eyebrow?: string;
  right?: ReactNode;
  glow?: "accent" | "iris";
  delay?: number;
}) {
  const glowCls =
    glow === "accent" ? "shadow-glow" : glow === "iris" ? "shadow-glow-iris" : "";
  return (
    <section
      className={`glass animate-fade-up p-4 ${glowCls} ${className}`}
      style={{ animationDelay: `${delay}ms` }}
    >
      {(eyebrow || right) && (
        <header className="mb-3 flex items-center justify-between gap-2">
          {eyebrow && <span className="label-eyebrow">{eyebrow}</span>}
          {right}
        </header>
      )}
      {children}
    </section>
  );
}
