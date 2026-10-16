"use client";

import { useTrace } from "@/components/ascii/use-trace";
import { stats } from "@/config/deck";
import { Slide, type SlideProps, Title } from "../slide";

const CELLS = 12;

export function Built(p: SlideProps) {
  // one shared meter that inks in under every number when the slide appears
  const step = useTrace(p.active, CELLS, 45);
  const inked = step ?? CELLS;
  return (
    <Slide {...p} label="What's built">
      <Title className="mb-[48px]">Built and tested, not a mockup.</Title>
      <dl className="grid grid-cols-3 gap-x-[64px] gap-y-[44px]">
        {stats.map((s) => (
          <div key={s.label} className="border-t border-border pt-[24px]">
            <dd className="font-serif text-[120px] leading-[0.9] tracking-tight">{s.value}</dd>
            <span aria-hidden className="mt-[18px] block font-mono text-[18px] tracking-[-0.05em]">
              <span className="text-secondary">{"█".repeat(inked)}</span>
              <span className="text-border">{"░".repeat(CELLS - inked)}</span>
            </span>
            <dt className="mt-[14px] font-mono text-[19px] uppercase tracking-[0.2em]">{s.label}</dt>
            <p className="mt-[6px] text-[21px] leading-[1.4] text-muted-foreground">{s.body}</p>
          </div>
        ))}
      </dl>
    </Slide>
  );
}
