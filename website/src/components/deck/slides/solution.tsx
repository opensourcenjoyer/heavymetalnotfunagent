"use client";

import { useTrace } from "@/components/ascii/use-trace";
import { pipeline } from "@/config/deck";
import { cn } from "@/lib/utils";
import { Label, Slide, type SlideProps, Title } from "../slide";

export function Solution(p: SlideProps) {
  // the four stages ink in left to right, like the site's meters
  const step = useTrace(p.active, pipeline.length, 380);
  const shown = step ?? pipeline.length;
  return (
    <Slide {...p} label="Solution" className="flex flex-col">
      <Title className="max-w-[1500px]">One agent. Plain language in, a reviewed trade out.</Title>
      <ol className="mt-[72px] grid grid-cols-4 gap-[40px]">
        {pipeline.map((s, i) => (
          <li key={s.step} className={cn("transition-opacity duration-300", i >= shown && "opacity-15")}>
            <div className="mb-[28px] flex items-center gap-[16px]" aria-hidden>
              <span className="h-[8px] flex-1 bg-primary" />
              <span className="font-mono text-[22px] text-accent">{i < pipeline.length - 1 ? "→" : "■"}</span>
            </div>
            <Label className="mb-[14px]">
              <span className="text-accent">{String(i + 1).padStart(2, "0")}</span> / {s.step}
            </Label>
            <h3 className="font-serif text-[44px] leading-[1.08]">{s.line}</h3>
            <p className="mt-[18px] text-[24px] leading-[1.45] text-muted-foreground">{s.body}</p>
          </li>
        ))}
      </ol>
      <dl className="mt-[112px] grid grid-cols-2 gap-[40px]">
        {[
          ["Interfaces", "Terminal REPL · fullscreen TUI · browser · one-shot -p"],
          ["Models", "Claude, or any self-hosted open-weights model (Ollama, vLLM)"],
        ].map(([k, v]) => (
          <div key={k} className="border-t border-border pt-[20px]">
            <dt className="font-mono text-[18px] uppercase tracking-[0.2em]">{k}</dt>
            <dd className="mt-[8px] text-[24px] text-muted-foreground">{v}</dd>
          </div>
        ))}
      </dl>
    </Slide>
  );
}
