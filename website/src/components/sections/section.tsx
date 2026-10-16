import { cn } from "@/lib/utils";

/** Numbered editorial section: mono label in the left rail, content on the right. */
export function Section({
  id,
  index,
  label,
  title,
  children,
  className,
}: {
  id: string;
  index: string;
  label: string;
  title: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section id={id} className={cn("scroll-mt-20 border-t border-border py-20 md:py-28", className)}>
      <div className="mx-auto grid max-w-6xl grid-cols-1 gap-10 px-6 md:grid-cols-12">
        <div className="md:col-span-3">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
            <span className="text-accent">{index}</span> / {label}
          </p>
        </div>
        <div className="md:col-span-9">
          <h2 className="mb-12 max-w-2xl font-serif text-4xl leading-[1.05] tracking-tight md:text-5xl">{title}</h2>
          {children}
        </div>
      </div>
    </section>
  );
}
