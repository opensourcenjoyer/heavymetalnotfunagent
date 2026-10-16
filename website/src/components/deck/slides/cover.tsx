import { Bear } from "@/components/bear/bear";
import { deck } from "@/config/deck";
import { Label, Slide, type SlideProps } from "../slide";

export function Cover(p: SlideProps) {
  return (
    <Slide {...p} label="Pitch" className="grid grid-cols-12 items-center gap-[48px]">
      <div className="col-span-7">
        <Label className="mb-[40px]">
          {deck.event} · {deck.version} · MIT
        </Label>
        <h1 className="font-serif text-[200px] leading-[0.9] tracking-tight">
          heavymetal<span className="text-primary">.</span>
        </h1>
        <p className="mt-[36px] max-w-[980px] font-serif text-[60px] leading-[1.05] tracking-tight">
          An open-source AI agent for Solana memecoins.
        </p>
        <p className="mt-[36px] max-w-[880px] text-[28px] leading-[1.45] text-muted-foreground">
          It researches tokens, reviews every swap with a second model and signs from its own wallet. Its public face is
          Wizzy, a read-only wizard bear on Telegram, X and the web.
        </p>
      </div>
      <div className="col-span-5 flex justify-end">
        <Bear className="deck-bear" />
      </div>
    </Slide>
  );
}
