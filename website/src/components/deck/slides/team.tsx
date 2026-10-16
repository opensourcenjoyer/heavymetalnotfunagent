import { Bear } from "@/components/bear/bear";
import { deck, team } from "@/config/deck";
import { Label, Slide, type SlideProps } from "../slide";

const TRY = [`git clone ${deck.repoUrl} && cd heavymetalnotfunagent`, "uv sync --extra dev && uv run heavymetal"];

export function Team(p: SlideProps) {
  return (
    <Slide {...p} label="Team" className="flex flex-col">
      <div className="grid grid-cols-12 gap-[64px]">
        <div className="col-span-7">
          <h2 className="font-serif text-[128px] leading-[0.95] tracking-tight">
            Read it. Fork it.
            <br />
            Then fund it.
          </h2>
          <dl className="mt-[56px] grid grid-cols-2 gap-[48px]">
            {team.map((t) => (
              <div key={t.name} className="border-t border-border pt-[20px]">
                <dt className="font-serif text-[56px] leading-none">{t.name}</dt>
                <dd className="mt-[14px] text-[26px] leading-tight">{t.role}</dd>
                <dd className="mt-[8px] font-mono text-[20px] text-muted-foreground">{t.handle}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="col-span-5 flex items-center justify-end">
          <Bear className="deck-bear deck-bear-sm" />
        </div>
      </div>
      <div className="mt-auto">
        <div className="mb-[14px] flex items-baseline justify-between">
          <Label>Try it</Label>
          <a href={deck.repoUrl} className="link-quiet font-mono text-[18px]">
            {deck.repo}
          </a>
        </div>
        <pre className="m-0 border border-border bg-card px-[26px] py-[18px] font-mono text-[20px] leading-[1.7]">
          {TRY.map((l) => (
            <span key={l} className="block">
              <span className="select-none text-muted-foreground">$ </span>
              {l}
            </span>
          ))}
        </pre>
        <p className="mt-[16px] font-mono text-[15px] text-muted-foreground">{deck.disclaimer}</p>
      </div>
    </Slide>
  );
}
