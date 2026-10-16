"use client";

import { useState } from "react";

import { reviewStages } from "@/config/site";
import { useTrace } from "./use-trace";

// One character of the diagram; `frame` marks borders and connectors, which are what the hover trace lights.
type Cell = { ch: string; frame: boolean };
type Row = Cell[];

const text = (s: string): Row => [...s].map((ch) => ({ ch, frame: false }));
const frame = (s: string): Row => [...s].map((ch) => ({ ch, frame: ch !== " " }));

/** One stage as a box of the given inner width and height (in lines, excluding top and bottom border). */
function box(i: number, inner: number, height: number): Row[] {
  const s = reviewStages[i];
  const body = [`${i + 1} ${s.title}`, "", ...s.items];
  while (body.length < height) body.push("");
  return [
    frame(`.${"-".repeat(inner)}.`),
    ...body.map((t) => [...frame("|"), ...text(` ${t}`.padEnd(inner)), ...frame("|")]),
    frame(`'${"-".repeat(inner)}'`),
  ];
}

const innerWidth = (i: number) =>
  Math.max(`${i + 1} ${reviewStages[i].title}`.length, ...reviewStages[i].items.map((t) => t.length)) + 2;
const tallest = Math.max(...reviewStages.map((s) => s.items.length + 2));

/** Boxes side by side, joined by --> on the title row. */
function horizontal(): Row[] {
  const cols = reviewStages.map((_, i) => box(i, innerWidth(i), tallest));
  return cols[0].map((_, y) => cols.flatMap((c, i) => [...(i > 0 ? (y === 1 ? frame("-->") : text("   ")) : []), ...c[y]]));
}

/** Boxes stacked, joined by | and v. */
function vertical(): Row[] {
  const inner = Math.max(...reviewStages.map((_, i) => innerWidth(i)));
  const mid = " ".repeat(Math.floor(inner / 2) + 1);
  return reviewStages.flatMap((s, i) => [
    ...(i > 0 ? [frame(`${mid}|`), frame(`${mid}v`)] : []),
    ...box(i, inner, s.items.length + 2),
  ]);
}

const H = horizontal();
const V = vertical();

function Diagram({ rows, axis, active, className }: { rows: Row[]; axis: "x" | "y"; active: boolean; className: string }) {
  const span = axis === "x" ? Math.max(...rows.map((r) => r.length)) : rows.length;
  const step = useTrace(active, span, axis === "x" ? 7 : 22);
  const tone = (c: Cell, at: number) => {
    if (!c.frame) return undefined;
    if (step === null || at >= step) return "text-muted-foreground";
    return at === step - 1 && step < span ? "text-secondary" : "text-accent";
  };
  return (
    <pre aria-hidden className={`m-0 w-fit font-mono text-[12px] leading-[1.45] [font-variant-ligatures:none] ${className}`}>
      {rows.map((row, y) => (
        <span key={y} className="block">
          {row.map((c, x) => (
            <span key={x} className={tone(c, axis === "x" ? x : y)}>
              {c.ch}
            </span>
          ))}
        </span>
      ))}
    </pre>
  );
}

/** The four review stages of heavymetal/review.py. On hover the frames and arrows are traced in reading order. */
export function ReviewFlow() {
  const [active, setActive] = useState(false);
  return (
    <figure className="m-0 overflow-x-auto" onPointerEnter={() => setActive(true)} onPointerLeave={() => setActive(false)}>
      <Diagram rows={H} axis="x" active={active} className="hidden lg:block" />
      <Diagram rows={V} axis="y" active={active} className="lg:hidden" />
      <figcaption className="sr-only">
        {reviewStages.map((s, i) => `${i + 1}. ${s.title}: ${s.items.join(", ")}.`).join(" ")}
      </figcaption>
    </figure>
  );
}
