"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";
import {
  BLINK_EVERY,
  BLINK_FOR,
  DOT_H,
  DOT_W,
  FPS,
  MOUTH_CYCLE,
  WIDTH,
  renderFrame,
  type Frame,
} from "@/lib/bear/engine";

const STATIC: Frame = { pose: { mouth: 0, blink: false }, field: null, hat: 1, sparkle: null };
const TOUCH_HOLD_MS = 2000;

/**
 * The bear from the CLI, as live Braille text. Idle it blinks. Under the pointer its dots part around the cursor,
 * the hat inks in from the brim, and it talks with sparkles round the hat tip, as it does while a reply streams.
 */
export function Bear({ className, interactive = true }: { className?: string; interactive?: boolean }) {
  const ref = useRef<HTMLPreElement>(null);

  useEffect(() => {
    const pre = ref.current;
    if (!pre) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!interactive || reduced) {
      pre.innerHTML = renderFrame(interactive ? STATIC : { ...STATIC, hat: 0 });
      return;
    }

    let hovered = false;
    let touchUntil = 0;
    let target = { x: DOT_W / 2, y: DOT_H / 2 };
    const pointer = { x: target.x, y: target.y };
    let amount = 0;
    let velocity = 0;
    let hat = 0;
    let visible = true;
    let raf = 0;
    let last = "";
    const start = performance.now();

    const toDots = (e: PointerEvent) => {
      const r = pre.getBoundingClientRect();
      return { x: ((e.clientX - r.left) / r.width) * DOT_W, y: ((e.clientY - r.top) / r.height) * DOT_H };
    };
    const onMove = (e: PointerEvent) => {
      target = toDots(e);
      if (!hovered) Object.assign(pointer, target);
      hovered = true;
    };
    const onLeave = () => {
      if (performance.now() > touchUntil) hovered = false;
    };
    const onDown = (e: PointerEvent) => {
      if (e.pointerType === "mouse") return;
      onMove(e);
      touchUntil = performance.now() + TOUCH_HOLD_MS;
    };

    const tick = (now: number) => {
      raf = requestAnimationFrame(tick);
      if (!visible) return;
      if (touchUntil && now > touchUntil) {
        touchUntil = 0;
        hovered = false;
      }
      const t = (now - start) / 1000;
      const active = hovered;

      // pointer eases toward the cursor; field strength is an underdamped spring, so the ink settles with a wobble
      pointer.x += (target.x - pointer.x) * 0.25;
      pointer.y += (target.y - pointer.y) * 0.25;
      velocity += ((active ? 1 : 0) - amount) * 0.08;
      velocity *= 0.8;
      amount = Math.max(0, amount + velocity);
      hat += ((active ? 1 : 0) - hat) * (active ? 0.06 : 0.04);

      const step = Math.floor(t * FPS);
      const blink = t % BLINK_EVERY < BLINK_FOR;
      const frame: Frame = {
        pose: { mouth: active ? MOUTH_CYCLE[step % MOUTH_CYCLE.length] : 0, blink },
        field: amount > 0.01 ? { x: pointer.x, y: pointer.y, amount } : null,
        hat: hat < 0.01 ? 0 : hat,
        sparkle: active ? Math.floor(step / 2) : null,
      };
      const html = renderFrame(frame);
      if (html !== last) {
        pre.innerHTML = html;
        last = html;
      }
    };

    // sparkles are not Braille glyphs; pin them to the Braille cell width so rows stay aligned
    const ro = new ResizeObserver(() => pre.style.setProperty("--cell", `${pre.scrollWidth / WIDTH}px`));
    ro.observe(pre);
    const io = new IntersectionObserver(([entry]) => (visible = entry.isIntersecting));
    io.observe(pre);
    pre.addEventListener("pointermove", onMove);
    pre.addEventListener("pointerleave", onLeave);
    pre.addEventListener("pointerdown", onDown);
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      ro.disconnect();
      pre.removeEventListener("pointermove", onMove);
      pre.removeEventListener("pointerleave", onLeave);
      pre.removeEventListener("pointerdown", onDown);
    };
  }, [interactive]);

  return (
    <figure className={cn("m-0", className)}>
      <pre
        ref={ref}
        aria-hidden
        className="bear select-none"
        dangerouslySetInnerHTML={{ __html: renderFrame({ ...STATIC, hat: 0 }) }}
      />
      <figcaption className="sr-only">Wizzy, a small bear in a wizard hat, drawn in Braille dots.</figcaption>
    </figure>
  );
}
