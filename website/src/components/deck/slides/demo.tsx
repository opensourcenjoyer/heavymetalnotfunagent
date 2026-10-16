"use client";

import { session } from "@/config/deck";
import { Slide, type SlideProps, Title } from "../slide";
import { Terminal } from "../terminal";

export function Demo(p: SlideProps) {
  return (
    <Slide {...p} label="Demo" className="flex flex-col">
      <Title className="mb-[40px] text-[72px] leading-[1.04]">One buy goes through. One injection doesn&rsquo;t.</Title>
      <Terminal title="heavymetal · terminal REPL" lines={session} active={p.active} />
      <p className="mt-[18px] font-mono text-[16px] uppercase tracking-[0.18em] text-muted-foreground">
        Illustrative session in the REPL&rsquo;s own formats. Numbers are examples.
      </p>
    </Slide>
  );
}
