"use client";

import { useState } from "react";

import { Sparkline } from "@/components/ascii/sparkline";
import { prophecies } from "@/config/site";
import { Section } from "./section";

export function Prophecies() {
  const [hover, setHover] = useState<number | null>(null);
  return (
    <Section id="prophecies" index="04" label="Prophecies" title="Claims that can be wrong, and are graded when they are.">
      <p className="mb-12 max-w-xl text-muted-foreground">
        Three a day by default, each a measurable claim made in code with a frozen baseline. Graded only after it matures,
        with data stamped after the claim. Missing data voids the claim. On Sunday the scoreboard names the wrong calls.
      </p>
      <div className="border-t border-border">
        <div className="grid grid-cols-[1fr_auto] gap-6 border-b border-border py-3 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground md:grid-cols-[1fr_8rem_6rem]">
          <span>Example scoreboard</span>
          <span className="hidden md:block">Trail</span>
          <span>Result</span>
        </div>
        {prophecies.map((p, i) => (
          <div
            key={p.claim}
            onPointerEnter={() => setHover(i)}
            onPointerLeave={() => setHover(null)}
            className="grid grid-cols-[1fr_auto] items-baseline gap-6 border-b border-border py-4 md:grid-cols-[1fr_8rem_6rem]"
          >
            <span>{p.claim}</span>
            <span className="hidden md:block">
              <Sparkline series={p.series} active={hover === i} dim={p.result !== "came true"} />
            </span>
            <span className={`font-mono text-xs uppercase tracking-[0.16em] ${p.result === "wrong" ? "text-foreground line-through decoration-secondary" : "text-muted-foreground"}`}>
              {p.result}
            </span>
          </div>
        ))}
      </div>
    </Section>
  );
}
