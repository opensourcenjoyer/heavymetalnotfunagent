import { deck } from "@/config/deck";
import { cn } from "@/lib/utils";

export type SlideProps = { index: number; total: number; current: boolean; active: boolean };

const pad = (n: number) => String(n).padStart(2, "0");

/** One 1920x1080 slide in the site's editorial frame: mono rail label on top, hairline footer with the counter. */
export function Slide({
  index,
  total,
  current,
  label,
  className,
  children,
}: Omit<SlideProps, "active"> & { label: string; className?: string; children: React.ReactNode }) {
  return (
    <section
      data-current={current}
      aria-roledescription="slide"
      aria-label={`${pad(index)} / ${label}`}
      className="deck-slide relative flex h-[1080px] w-[1920px] flex-col overflow-hidden bg-background px-[128px] pb-[64px] pt-[72px]"
    >
      <header className="flex items-baseline justify-between font-mono text-[18px] uppercase tracking-[0.2em] text-muted-foreground">
        <p>
          <span className="text-accent">{pad(index)}</span> / {label}
        </p>
        <p className="normal-case tracking-tight text-foreground">
          heavymetal<span className="text-primary">.</span>
        </p>
      </header>
      <div className={cn("min-h-0 flex-1 pb-[32px] pt-[60px]", className)}>{children}</div>
      <footer className="flex items-baseline justify-between border-t border-border pt-[22px] font-mono text-[16px] uppercase tracking-[0.2em] text-muted-foreground">
        <span>{deck.event}</span>
        <span>
          {pad(index)} / {pad(total - 1)}
        </span>
      </footer>
    </section>
  );
}

export function Title({ className, children }: { className?: string; children: React.ReactNode }) {
  return <h2 className={cn("font-serif text-[88px] leading-[1.02] tracking-tight", className)}>{children}</h2>;
}

export function Lead({ className, children }: { className?: string; children: React.ReactNode }) {
  return <p className={cn("text-[28px] leading-[1.45] text-muted-foreground", className)}>{children}</p>;
}

export function Label({ className, children }: { className?: string; children: React.ReactNode }) {
  return <p className={cn("font-mono text-[18px] uppercase tracking-[0.2em] text-muted-foreground", className)}>{children}</p>;
}
