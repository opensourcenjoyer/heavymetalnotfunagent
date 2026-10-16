"use client";

import { useTrace } from "./use-trace";

const SPARK = "▁▂▃▄▅▆▇█"; // heavymetal/ui_signals.py

/** ui_signals.py sparkline. When `active`, it is redrawn left to right, one bar per step. */
export function Sparkline({ series, active, dim }: { series: readonly number[]; active: boolean; dim?: boolean }) {
  const step = useTrace(active, series.length, 45);
  const shown = step ?? series.length;
  const max = Math.max(...series, 1);
  const bars = series.map((v) => SPARK[Math.min(SPARK.length - 1, Math.round((v / max) * (SPARK.length - 1)))]);
  return (
    <span aria-hidden className="font-mono tracking-[0.05em]">
      <span className={dim ? "text-muted-foreground" : "text-secondary"}>{bars.slice(0, shown).join("")}</span>
      <span className="text-border">{"▁".repeat(series.length - shown)}</span>
    </span>
  );
}
