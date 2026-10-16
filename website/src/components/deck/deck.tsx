"use client";

import { useEffect, useSyncExternalStore } from "react";

import { Business } from "./slides/business";
import { Built } from "./slides/built";
import { Cover } from "./slides/cover";
import { Demo } from "./slides/demo";
import { OpenSource } from "./slides/open-source";
import { Problem } from "./slides/problem";
import { Review } from "./slides/review";
import { Solution } from "./slides/solution";
import { Team } from "./slides/team";
import { Wizzy } from "./slides/wizzy";

const SLIDES = [Cover, Problem, Solution, Review, Demo, Wizzy, OpenSource, Built, Business, Team];
const LAST = SLIDES.length - 1;
const W = 1920;
const H = 1080;

const clamp = (n: number) => Math.max(0, Math.min(LAST, n));
const go = (n: number) => {
  window.location.hash = String(clamp(n));
};

// The slide number lives in the URL hash (#3), so reloads and shared links land on the same slide.
const onHash = (cb: () => void) => {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
};
const readHash = () => clamp(Number.parseInt(window.location.hash.slice(1), 10) || 0);

const onResize = (cb: () => void) => {
  window.addEventListener("resize", cb);
  return () => window.removeEventListener("resize", cb);
};
const readScale = () => Math.min(window.innerWidth / W, window.innerHeight / H);

const never = () => () => {};

/**
 * The pitch deck: a fixed 1920x1080 stage scaled to the window. Arrows, Space, PgUp/PgDn, Home/End and F
 * (fullscreen). Printing lays every slide out on its own 1920x1080 page (see deck.css).
 */
export function Deck() {
  const current = useSyncExternalStore(onHash, readHash, () => 0);
  const scale = useSyncExternalStore(onResize, readScale, () => 1);
  const mounted = useSyncExternalStore(never, () => true, () => false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const now = readHash();
      if (["ArrowRight", "ArrowDown", "PageDown", " ", "Enter"].includes(e.key)) go(now + 1);
      else if (["ArrowLeft", "ArrowUp", "PageUp", "Backspace"].includes(e.key)) go(now - 1);
      else if (e.key === "Home") go(0);
      else if (e.key === "End") go(LAST);
      else if (e.key === "f" || e.key === "F") {
        if (document.fullscreenElement) void document.exitFullscreen();
        else void document.documentElement.requestFullscreen();
      } else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="deck-screen fixed inset-0 overflow-hidden bg-muted" aria-roledescription="carousel" aria-label="heavymetal pitch deck">
      <div
        className="deck-stage absolute left-1/2 top-1/2 shadow-[0_0_0_1px_var(--border)]"
        style={{ width: W, height: H, transform: `translate(-50%, -50%) scale(${scale})` }}
      >
        {SLIDES.map((S, i) => (
          <S key={i} index={i} total={SLIDES.length} current={i === current} active={mounted && i === current} />
        ))}
      </div>

      <nav aria-label="Slides" className="deck-controls fixed bottom-3 right-3 flex items-center gap-1 font-mono text-xs">
        <button
          type="button"
          onClick={() => go(current - 1)}
          disabled={current === 0}
          aria-label="Previous slide"
          className="border border-border bg-background px-2 py-1 hover:bg-card disabled:opacity-40"
        >
          ←
        </button>
        <span className="min-w-14 text-center text-muted-foreground" aria-live="polite">
          {String(current).padStart(2, "0")} / {String(LAST).padStart(2, "0")}
        </span>
        <button
          type="button"
          onClick={() => go(current + 1)}
          disabled={current === LAST}
          aria-label="Next slide"
          className="border border-border bg-background px-2 py-1 hover:bg-card disabled:opacity-40"
        >
          →
        </button>
      </nav>
      <div aria-hidden className="deck-controls fixed inset-x-0 bottom-0 h-[2px]">
        <div className="h-full bg-primary transition-[width] duration-300" style={{ width: `${(current / LAST) * 100}%` }} />
      </div>
    </div>
  );
}
