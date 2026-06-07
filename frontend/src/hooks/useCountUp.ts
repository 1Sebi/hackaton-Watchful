import { useEffect, useRef, useState } from "react";

// Animate a number toward `target` with an ease-out tween. Used for KPI stats so
// values count up instead of snapping. Respects prefers-reduced-motion.
export function useCountUp(target: number, duration = 600): number {
  const [value, setValue] = useState(target);
  const fromRef = useRef(target);
  const startRef = useRef(0);
  const rafRef = useRef(0);

  useEffect(() => {
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce || target === value) {
      setValue(target);
      return;
    }
    fromRef.current = value;
    startRef.current = 0;
    const tick = (t: number) => {
      if (!startRef.current) startRef.current = t;
      const p = Math.min((t - startRef.current) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(fromRef.current + (target - fromRef.current) * eased);
      if (p < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, duration]);

  return value;
}
