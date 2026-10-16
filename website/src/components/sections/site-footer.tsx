import { Bear } from "@/components/bear/bear";
import { site } from "@/config/site";

export function SiteFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-6xl flex-col gap-10 px-6 py-16 md:flex-row md:items-end md:justify-between">
        <div className="space-y-4">
          <Bear interactive={false} className="bear-mark" />
          <p className="max-w-sm font-mono text-xs leading-relaxed text-muted-foreground">
            {site.disclaimer} The trading agent in the same repo signs real transactions;{" "}
            <a className="link-quiet text-foreground" href={site.links.risks}>
              read the risks first
            </a>
            .
          </p>
        </div>
        <nav aria-label="Elsewhere" className="flex gap-6 font-mono text-xs uppercase tracking-[0.16em]">
          <a className="link-quiet" href={site.links.x}>X</a>
          <a className="link-quiet" href={site.links.github}>GitHub</a>
        </nav>
      </div>
    </footer>
  );
}
