import { Bear } from "@/components/bear/bear";
import { buttonVariants } from "@/components/ui/button";
import { site } from "@/config/site";
import { cn } from "@/lib/utils";

export function Hero() {
  return (
    <section id="top" className="mx-auto grid max-w-6xl grid-cols-1 items-center gap-12 px-6 pb-24 pt-16 md:grid-cols-12 md:pt-24">
      <div className="md:col-span-6">
        <p className="mb-8 font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
          Solana · read-only · Telegram, X, web
        </p>
        <h1 className="font-serif text-5xl leading-[0.98] tracking-tight md:text-7xl">
          A small wizard bear who reads Solana tokens.
        </h1>
        <p className="mt-8 max-w-md text-lg leading-relaxed text-muted-foreground">
          Send a ticker, a contract or a wallet. Wizzy computes the facts in code from the chain, and the model only
          phrases them. Today it never trades.
        </p>
        <div className="mt-10 flex flex-wrap gap-3">
          <a href={site.links.github} className={cn(buttonVariants({ size: "lg" }), "font-mono text-xs uppercase tracking-[0.14em]")}>
            Open GitHub
          </a>
          <a href={site.links.x} className={cn(buttonVariants({ variant: "outline", size: "lg" }), "font-mono text-xs uppercase tracking-[0.14em]")}>
            Tag on X
          </a>
        </div>
      </div>
      <div className="flex justify-center md:col-span-6 md:justify-end">
        <Bear className="bear-hero" />
      </div>
    </section>
  );
}
