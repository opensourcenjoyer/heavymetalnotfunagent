"use client";

import { useTrace } from "@/components/ascii/use-trace";
import { evalStats, reviewSteps, verdicts } from "@/config/deck";
import { cn } from "@/lib/utils";
import { Label, Slide, type SlideProps, Title } from "../slide";

const MARK = { go: "text-primary", stop: "text-destructive", hold: "text-muted-foreground" } as const;

export function Review(p: SlideProps) {
  const step = useTrace(p.active, verdicts.length, 160);
  const shown = step ?? verdicts.length;
  return (
    <Slide {...p} label="Swap review" className="grid grid-cols-12 gap-[64px]">
      <div className="col-span-7">
        <Title className="text-[72px] leading-[1.04]">A second model checks every swap before it is signed.</Title>
        <ol className="mt-[44px] border-t border-border">
          {reviewSteps.map((s, i) => (
            <li key={s.name} className="grid grid-cols-[72px_1fr] border-b border-border py-[18px]">
              <span className="pt-[10px] font-mono text-[18px] text-muted-foreground">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <h3 className="font-serif text-[36px] leading-tight">{s.name}</h3>
                <p className="mt-[4px] text-[22px] leading-[1.4] text-muted-foreground">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
      <div className="col-span-5 flex flex-col">
        <div className="border border-border bg-card px-[32px] py-[26px]">
          <Label className="mb-[16px]">One verdict per swap</Label>
          <ul className="font-mono text-[20px] leading-[1.95]">
            {verdicts.map((v, i) => (
              <li key={v.name} className={cn("grid grid-cols-[28px_290px_1fr] items-baseline", i >= shown && "invisible")}>
                <span aria-hidden className={MARK[v.tone]}>
                  █
                </span>
                <span>{v.name}</span>
                <span className="font-sans text-[19px] text-muted-foreground">{v.body}</span>
              </li>
            ))}
          </ul>
        </div>
        <dl className="mt-[36px] grid grid-cols-3 gap-[24px]">
          {evalStats.map((s, i) => (
            <div key={i} className="border-t border-border pt-[16px]">
              <dd className="font-serif text-[56px] leading-none">{s.value}</dd>
              <dt className="mt-[10px] font-mono text-[15px] uppercase tracking-[0.18em] text-muted-foreground">{s.label}</dt>
            </div>
          ))}
        </dl>
        <p className="mt-[18px] text-[18px] leading-[1.4] text-muted-foreground">
          TypeSafe Jev 1.13 on our 13 hand-written review cases, real model calls. A smoke test, not a benchmark.
        </p>
      </div>
    </Slide>
  );
}
