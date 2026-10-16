import { buttonVariants } from "@/components/ui/button";
import { nav, site } from "@/config/site";
import { cn } from "@/lib/utils";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/90 backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
        <a href="#top" className="font-mono text-sm font-medium tracking-tight">
          wizzy<span className="text-primary">.</span>
        </a>
        <nav aria-label="Sections" className="hidden items-center gap-7 md:flex">
          {nav.map((n) => (
            <a key={n.href} href={n.href} className="link-quiet font-mono text-xs uppercase tracking-[0.16em] text-muted-foreground">
              {n.label}
            </a>
          ))}
        </nav>
        <a href={site.links.github} className={cn(buttonVariants({ variant: "outline", size: "sm" }), "font-mono text-xs")}>
          GitHub
        </a>
      </div>
    </header>
  );
}
