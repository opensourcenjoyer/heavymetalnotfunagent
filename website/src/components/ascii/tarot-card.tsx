"use client";

import { useState } from "react";

import { useTrace } from "./use-trace";

const W = 26; // inner width in characters
const H = 9; // inner height in lines

const center = (s: string) => {
  const pad = Math.max(0, W - s.length);
  return " ".repeat(Math.floor(pad / 2)) + s + " ".repeat(Math.ceil(pad / 2));
};

// Perimeter cells clockwise from the top-left corner: the order the border is redrawn on hover.
const PERIMETER: [number, number][] = [
  ...Array.from({ length: W + 2 }, (_, x) => [x, 0] as [number, number]),
  ...Array.from({ length: H }, (_, y) => [W + 1, y + 1] as [number, number]),
  ...Array.from({ length: W + 2 }, (_, x) => [W + 1 - x, H + 1] as [number, number]),
  ...Array.from({ length: H }, (_, y) => [0, H - y] as [number, number]),
];
const ORDER = new Map(PERIMETER.map(([x, y], i) => [`${x},${y}`, i]));

function wrap(text: string, width: number) {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(" ")) {
    if ((line + " " + word).trim().length > width) {
      lines.push(line);
      line = word;
    } else line = (line + " " + word).trim();
  }
  return [...lines, line];
}

/** A box-drawn tarot card. On hover the frame is redrawn clockwise in the accent colour, one glyph at a time. */
export function TarotCard({ position, name, line, strength }: { position: string; name: string; line: string; strength: number }) {
  const [active, setActive] = useState(false);
  const step = useTrace(active, PERIMETER.length, 9);

  const bars = Math.round(strength * 10);
  const body = [
    "",
    center(position.toUpperCase()),
    "",
    center(name),
    center("·  *  ·"),
    ...wrap(line, W - 4).map(center),
  ];
  while (body.length < H - 1) body.push("");
  body.push(center(`[${"#".repeat(bars)}${".".repeat(10 - bars)}]`));

  const rows: string[][] = [];
  // plain ASCII frame: box-drawing glyphs are not in the web font subset and would fall back at another width
  rows.push([".", ..."-".repeat(W), "."]);
  for (const l of body.slice(0, H)) rows.push(["|", ...l.padEnd(W).slice(0, W), "|"]);
  rows.push(["'", ..."-".repeat(W), "'"]);

  return (
    <pre
      onPointerEnter={() => setActive(true)}
      onPointerLeave={() => setActive(false)}
      aria-label={`${position}: ${name}, ${line}`}
      className="m-0 w-fit font-mono text-[13px] leading-[1.35] text-foreground"
    >
      {rows.map((row, y) => (
        <span key={y} className="block">
          {row.map((ch, x) => {
            const i = ORDER.get(`${x},${y}`);
            const lit = i !== undefined && step !== null && i < step;
            const head = i !== undefined && step !== null && i === step - 1 && step < PERIMETER.length;
            return (
              <span key={x} className={head ? "text-secondary" : lit ? "text-accent" : undefined}>
                {ch}
              </span>
            );
          })}
        </span>
      ))}
    </pre>
  );
}
