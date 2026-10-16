"use client";

import { useState } from "react";

import { omens } from "@/config/site";
import { useTrace } from "./use-trace";

const CELLS = 16;

function Meter({ level, active }: { level: number; active: boolean }) {
  const full = level * (CELLS / 4);
  const step = useTrace(active, full, 28);
  const inked = step ?? full;
  return (
    <span className="font-mono tracking-[-0.05em]" aria-hidden>
      <span className="text-secondary">{"█".repeat(inked)}</span>
      <span className="text-border">{"░".repeat(CELLS - inked)}</span>
    </span>
  );
}

/** cursed, hexed, murky, blessed as the TUI's █░ meters; hovering a row scries it again, cell by cell. */
export function OmenScale() {
  const [hover, setHover] = useState<string | null>(null);
  return (
    <ul className="divide-y divide-border border-y border-border">
      {omens.map((o) => (
        <li
          key={o.kind}
          onPointerEnter={() => setHover(o.kind)}
          onPointerLeave={() => setHover(null)}
          className="grid grid-cols-[5.5rem_1fr] items-baseline gap-x-6 gap-y-2 py-4"
        >
          <span className="font-mono text-xs uppercase tracking-[0.18em]">{o.kind}</span>
          <Meter level={o.level} active={hover === o.kind} />
          <span className="col-start-2 text-sm text-muted-foreground">
            <span className="text-foreground">{o.line}</span> {o.meaning}
          </span>
        </li>
      ))}
    </ul>
  );
}
