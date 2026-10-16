import { OmenScale } from "@/components/ascii/omen-scale";
import { Badge } from "@/components/ui/badge";
import { wizzyFeatures } from "@/config/deck";
import { Lead, Slide, type SlideProps, Title } from "../slide";

export function Wizzy(p: SlideProps) {
  return (
    <Slide {...p} label="Wizzy" className="grid grid-cols-12 gap-[72px]">
      <div className="col-span-6 flex flex-col">
        <Title className="text-[76px] leading-[1.02]">Wizzy can read the chain. It cannot touch it.</Title>
        <Lead className="mt-[28px] text-[25px]">
          The public face of heavymetal on Telegram, X and the web. It shares the audit code but never loads a wallet
          and never trades. Facts are computed in code; the model only phrases them.
        </Lead>
        <ul className="mt-auto grid grid-cols-2 gap-x-[40px] border-t border-border">
          {wizzyFeatures.map((f) => (
            <li key={f.name} className="border-b border-border py-[12px]">
              <code className="block font-mono text-[20px] text-accent">{f.name}</code>
              <span className="text-[20px] text-muted-foreground">{f.body}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="col-span-6 flex flex-col justify-between">
        <div className="border border-border bg-card px-[36px] py-[28px]">
          <div className="mb-[18px] flex items-center justify-between">
            <span className="font-mono text-[22px]">$EXAMPLE</span>
            <Badge variant="outline" className="h-auto rounded-none px-[10px] py-[4px] font-mono text-[15px] uppercase tracking-[0.18em]">
              murky
            </Badge>
          </div>
          <p className="font-serif text-[31px] leading-[1.25]">
            The waters are murky. Mint and freeze authorities are revoked, yet ten wallets hold most of the supply and
            the pool is thin for its volume. The runes ask for patience, not haste.
          </p>
          <p className="mt-[16px] font-mono text-[16px] text-muted-foreground">
            full scroll at /s/example-7f3a1c · lesson: holder concentration
          </p>
        </div>
        <div className="deck-zoom">
          <OmenScale />
        </div>
      </div>
    </Slide>
  );
}
