import { craft } from "@/config/site";
import { Section } from "./section";

export function Craft() {
  return (
    <Section id="craft" index="02" label="Craft" title="Eight things the bear knows how to do.">
      <ol className="border-t border-border">
        {craft.map((c, i) => (
          <li key={c.name} className="grid grid-cols-[2.5rem_1fr] gap-x-6 gap-y-2 border-b border-border py-6 md:grid-cols-[2.5rem_14rem_1fr]">
            <span className="font-mono text-xs text-muted-foreground">{String(i + 1).padStart(2, "0")}</span>
            <div>
              <h3 className="font-serif text-2xl leading-tight">{c.name}</h3>
              <code className="font-mono text-xs text-accent">{c.command}</code>
            </div>
            <p className="col-start-2 max-w-xl text-muted-foreground md:col-start-3">{c.body}</p>
          </li>
        ))}
      </ol>
    </Section>
  );
}
