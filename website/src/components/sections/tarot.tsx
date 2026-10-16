import { TarotCard } from "@/components/ascii/tarot-card";
import { spread } from "@/config/site";
import { Section } from "./section";

export function Tarot() {
  return (
    <Section id="tarot" index="03" label="Wallet tarot" title="Three cards, drawn by rules, not by chance.">
      <p className="mb-12 max-w-xl text-muted-foreground">
        The past comes from trade history, the present from holdings, the future from the omens of what the wallet
        holds. Ties are broken by the wallet and the UTC date, so the same data gives the same spread all day.
      </p>
      <div className="flex flex-wrap gap-6 overflow-x-auto">
        {spread.map((c) => (
          <TarotCard key={c.position} {...c} />
        ))}
      </div>
    </Section>
  );
}
