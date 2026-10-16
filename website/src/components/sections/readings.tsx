import { OmenScale } from "@/components/ascii/omen-scale";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Section } from "./section";

export function Readings() {
  return (
    <Section id="readings" index="01" label="Readings" title="Every reading starts as numbers from the chain.">
      <div className="grid items-start gap-12 lg:grid-cols-2">
        <Card className="rounded-none border-border bg-card shadow-none">
          <CardHeader className="flex flex-row items-center justify-between gap-4">
            <span className="font-mono text-sm">$EXAMPLE</span>
            <Badge variant="outline" className="rounded-none font-mono text-[10px] uppercase tracking-[0.18em]">
              murky
            </Badge>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="font-serif text-xl leading-snug">
              The waters are murky. Mint and freeze authorities are revoked, yet ten wallets hold most of the supply and
              the pool is thin for its volume. The runes ask for patience, not haste.
            </p>
            <p className="font-mono text-xs text-muted-foreground">full scroll at /s/example-7f3a1c · lesson: holder concentration</p>
          </CardContent>
        </Card>
        <div>
          <p className="mb-6 max-w-md text-muted-foreground">
            A ticker, contract, pump.fun or DexScreener link, or a wallet, sent in a DM or as a mention. The omen comes
            from the code-only audit; established tokens such as USDC are never called cursed.
          </p>
          <OmenScale />
        </div>
      </div>
    </Section>
  );
}
