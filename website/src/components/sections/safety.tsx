import { safety } from "@/config/site";
import { Section } from "./section";

export function Safety() {
  return (
    <Section id="safety" index="05" label="Safety" title="Today it reads the chain. It cannot touch it.">
      <p className="mb-12 max-w-xl text-muted-foreground">
        This is the public bear as it ships now: a read-only build with no wallet anywhere in reach.
      </p>
      <dl className="grid gap-x-12 gap-y-10 sm:grid-cols-2">
        {safety.map((s) => (
          <div key={s.title} className="border-t border-border pt-5">
            <dt className="mb-2 font-mono text-xs uppercase tracking-[0.16em]">{s.title}</dt>
            <dd className="text-muted-foreground">{s.body}</dd>
          </div>
        ))}
      </dl>
    </Section>
  );
}
