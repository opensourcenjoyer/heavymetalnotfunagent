/**
 * Braille bear engine. Same dot model as heavymetal/mascot.py: every character is a 2x4 cell of dots, and frames
 * are made by moving dots and re-encoding, so the art is always real Braille text. data.json is exported from
 * mascot.py by scripts/gen-bear.py; regenerate it instead of editing it.
 */
import data from "./data.json";

export const WIDTH = data.width;
export const HEIGHT = data.height;
export const DOT_W = WIDTH * 2;
export const DOT_H = HEIGHT * 4;
export const FPS = data.fps;
export const MOUTH_CYCLE = data.mouthCycle;
export const BLINK_EVERY = data.blinkEvery;
export const BLINK_FOR = data.blinkFor;

const BLANK = "⠀"; // blank Braille cell: same advance width as the inked ones, unlike a space

// (dy, dx, bit), as _BITS in mascot.py
const BITS: [number, number, number][] = [
  [0, 0, 0x01], [1, 0, 0x02], [2, 0, 0x04], [0, 1, 0x08],
  [1, 1, 0x10], [2, 1, 0x20], [3, 0, 0x40], [3, 1, 0x80],
];

const BIT_AT = new Uint8Array(8); // index (dy << 1) | dx
for (const [dy, dx, bit] of BITS) BIT_AT[(dy << 1) | dx] = bit;

export type Pose = { mouth: number; blink: boolean };
type Dot = [number, number];

function decode(rows: string[]): Dot[] {
  const dots: Dot[] = [];
  rows.forEach((line, r) => {
    [...line].forEach((ch, c) => {
      const v = ch === " " ? 0 : ch.codePointAt(0)! - 0x2800;
      for (const [dy, dx, bit] of BITS) if (v & bit) dots.push([c * 2 + dx, r * 4 + dy]);
    });
  });
  return dots;
}

const POSE_DOTS = new Map<string, Dot[]>(
  Object.entries(data.poses).map(([k, rows]) => [k, decode(rows as string[])]),
);
const FACE = new Set(data.face.map(([x, y]) => y * DOT_W + x));
// Hat cells from the brim up to the tip, left to right within a row: the order the ink fills them.
const HAT_FILL_ORDER = [...data.hatCells].sort((a, b) => b[1] - a[1] || a[0] - b[0]).map(([c, r]) => r * WIDTH + c);
const SPARKLES = data.sparkles as [number, number, string][][];

export type Field = {
  /** pointer in dot coordinates */
  x: number;
  y: number;
  /** 0..1, how strongly dots are pushed away */
  amount: number;
};

export type Frame = {
  pose: Pose;
  field: Field | null;
  /** 0..1 share of hat cells inked in the primary colour */
  hat: number;
  /** sparkle phase, or null for none */
  sparkle: number | null;
};

const RADIUS = 13; // dots
const PUSH = 6; // dots at the centre of the field

/** Render one frame to HTML: Braille rows with hat cells and sparkles wrapped in spans. */
export function renderFrame(f: Frame): string {
  const cells = new Uint8Array(WIDTH * HEIGHT);
  const dots = POSE_DOTS.get(`${f.pose.mouth}${f.pose.blink ? 1 : 0}`)!;
  // Cells are ~1:2 (w:h) and hold 2x4 dots, so dot spacing is equal on both axes: plain distances work.
  for (const [x0, y0] of dots) {
    let x = x0;
    let y = y0;
    if (f.field && f.field.amount > 0.001 && !FACE.has(y0 * DOT_W + x0)) {
      const dx = x0 - f.field.x;
      const dy = y0 - f.field.y;
      const d = Math.hypot(dx, dy);
      if (d < RADIUS && d > 0.01) {
        const k = (1 - d / RADIUS) ** 2 * PUSH * f.field.amount;
        x = Math.round(x0 + (dx / d) * k);
        y = Math.round(y0 + (dy / d) * k);
      }
    }
    if (x < 0 || y < 0 || x >= DOT_W || y >= DOT_H) continue;
    const c = x >> 1;
    const r = y >> 2;
    cells[r * WIDTH + c] |= BIT_AT[((y & 3) << 1) | (x & 1)];
  }

  const inked = new Set(HAT_FILL_ORDER.slice(0, Math.round(f.hat * HAT_FILL_ORDER.length)));
  const sparks = new Map<number, string>();
  if (f.sparkle !== null) {
    for (const [c, r, ch] of SPARKLES[f.sparkle % SPARKLES.length]) {
      if (!cells[r * WIDTH + c]) sparks.set(r * WIDTH + c, ch);
    }
  }

  let html = "";
  for (let r = 0; r < HEIGHT; r++) {
    let run = "";
    let runHat = false;
    const flush = () => {
      if (run) html += runHat ? `<span class="bear-hat">${run}</span>` : run;
      run = "";
    };
    for (let c = 0; c < WIDTH; c++) {
      const i = r * WIDTH + c;
      const spark = sparks.get(i);
      if (spark) {
        flush();
        html += `<span class="bear-spark">${spark}</span>`;
        continue;
      }
      const hat = inked.has(i);
      if (hat !== runHat) {
        flush();
        runHat = hat;
      }
      run += cells[i] ? String.fromCodePoint(0x2800 + cells[i]) : BLANK;
    }
    flush();
    if (r < HEIGHT - 1) html += "\n";
  }
  return html;
}
