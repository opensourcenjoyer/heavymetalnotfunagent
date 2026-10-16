"use client";

import { Fragment } from "react";

import { useTrace } from "@/components/ascii/use-trace";
import type { TermLine } from "@/config/deck";
import { cn } from "@/lib/utils";

const VERDICT = /(EXECUTE|INJECTION_BLOCK)/;

function Verdicts({ text }: { text: string }) {
  return text.split(VERDICT).map((part, i) =>
    part === "EXECUTE" ? (
      <span key={i} className="bg-primary px-[6px] text-primary-foreground">
        {part}
      </span>
    ) : part === "INJECTION_BLOCK" ? (
      <span key={i} className="bg-destructive px-[6px] text-background">
        {part}
      </span>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

/** The REPL, replayed line by line while the slide is shown. Off-screen, printed or reduced motion: all lines. */
export function Terminal({ title, lines, active }: { title: string; lines: TermLine[]; active: boolean }) {
  const step = useTrace(active, lines.length, 420);
  const shown = step ?? lines.length;
  return (
    <figure className="m-0 border border-border bg-card">
      <figcaption className="flex items-center justify-between border-b border-border px-[28px] py-[14px] font-mono text-[16px] uppercase tracking-[0.2em] text-muted-foreground">
        <span>{title}</span>
        <span aria-hidden>
          <span className="text-primary">■</span> <span className="text-secondary">■</span>{" "}
          <span className="text-accent">■</span>
        </span>
      </figcaption>
      <pre className="m-0 whitespace-pre px-[28px] py-[24px] font-mono text-[23px] leading-[1.62]">
        {lines.map((l, i) => (
          <span
            key={i}
            className={cn(
              "block min-h-[1.62em]",
              i >= shown && "invisible",
              l.kind === "dim" && "text-muted-foreground",
              (l.kind === "go" || l.kind === "stop") && "font-medium",
            )}
          >
            {l.kind === "prompt" && <span className="select-none text-muted-foreground">{">> "}</span>}
            <Verdicts text={l.text} />
            {i === shown - 1 && step !== null && step < lines.length && (
              <span className="ml-1 inline-block animate-pulse text-accent">▍</span>
            )}
          </span>
        ))}
      </pre>
    </figure>
  );
}
