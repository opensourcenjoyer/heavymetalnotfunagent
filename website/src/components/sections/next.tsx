import { ReviewFlow } from "@/components/ascii/review-flow";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { risks, site, verdicts } from "@/config/site";
import { Section } from "./section";

export function Next() {
  return (
    <Section id="next" index="06" label="Next" title="One agent: reads, decides, executes.">
      <div className="mb-14 max-w-xl space-y-4 text-muted-foreground">
        <p>
          <Badge variant="outline" className="mr-2 rounded-none align-middle font-mono text-[10px] uppercase tracking-[0.18em]">
            planned
          </Badge>
          Wizzy and heavymetal, the trading agent in the same repo, become one agent. The bear keeps its readings and
          gains a wallet. Every swap passes the review heavymetal already runs in front of every trade today.
        </p>
      </div>

      <h3 className="mb-6 font-mono text-xs uppercase tracking-[0.18em]">Swap review</h3>
      <ReviewFlow />
      <p className="mt-6 max-w-xl text-sm text-muted-foreground">
        Facts are computed in code first, then a reviewer answers narrow questions in one call. It sees user messages
        and tool results apart, so only the user can authorize. Every question, probability and verdict is stored. These are the defaults: the review gates trades, and it can be set to advise-only or off.
      </p>

      <h3 className="mb-2 mt-16 font-mono text-xs uppercase tracking-[0.18em]">Verdicts</h3>
      <ol className="border-t border-border">
        {verdicts.map((v) => (
          <li key={v.name} className="group grid grid-cols-1 gap-x-6 gap-y-1 border-b border-border py-3 md:grid-cols-[13rem_1fr]">
            <code className="font-mono text-xs transition-colors duration-150 group-hover:text-accent">{v.name}</code>
            <span className="text-sm text-muted-foreground">{v.line}</span>
          </li>
        ))}
      </ol>

      <Card className="mt-16 rounded-none border-border bg-card shadow-none ring-0">
        <CardHeader>
          <p className="font-mono text-xs uppercase tracking-[0.18em]">Before funding a wallet</p>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm text-muted-foreground">
            {risks.map((r) => (
              <li key={r} className="grid grid-cols-[1.25rem_1fr]">
                <span className="font-mono text-secondary">-</span>
                <span>{r}</span>
              </li>
            ))}
          </ul>
          <a href={site.links.risks} className="link-quiet mt-6 inline-block font-mono text-xs text-foreground">
            Full risks in the README
          </a>
        </CardContent>
      </Card>
    </Section>
  );
}
