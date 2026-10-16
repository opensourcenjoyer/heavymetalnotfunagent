"use client";

import { useEffect, useState } from "react";

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Step counter for glyph-by-glyph drawing. While `active`, counts 0..n one step every `ms`; otherwise null.
 * Under reduced motion it jumps straight to n.
 */
export function useTrace(active: boolean, n: number, ms: number): number | null {
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (!active || reducedMotion()) return;
    let i = 0;
    const id = window.setInterval(() => {
      i = Math.min(i + 1, n);
      setStep(i);
      if (i >= n) window.clearInterval(id);
    }, ms);
    return () => {
      window.clearInterval(id);
      setStep(0);
    };
  }, [active, n, ms]);

  // `active` only turns true after a pointer event, so window is always defined here
  if (!active) return null;
  return reducedMotion() ? n : step;
}
