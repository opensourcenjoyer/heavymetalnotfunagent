import { problems } from "@/config/deck";
import { Slide, type SlideProps, Title } from "../slide";

export function Problem(p: SlideProps) {
  return (
    <Slide {...p} label="Problem">
      <Title className="mb-[48px] max-w-[1400px]">One trade, five tabs, and a rug at the end.</Title>
      <ol className="border-t border-border">
        {problems.map((x, i) => (
          <li key={x.name} className="grid grid-cols-[96px_560px_1fr] items-baseline border-b border-border py-[22px]">
            <span className="font-mono text-[18px] text-muted-foreground">{String(i + 1).padStart(2, "0")}</span>
            <h3 className="font-serif text-[40px] leading-tight">{x.name}</h3>
            <p className="text-[25px] leading-[1.4] text-muted-foreground">{x.body}</p>
          </li>
        ))}
      </ol>
    </Slide>
  );
}
