import { revenue, roadmap } from "@/config/deck";
import { cn } from "@/lib/utils";
import { Label, Slide, type SlideProps, Title } from "../slide";

export function Business(p: SlideProps) {
  return (
    <Slide {...p} label="Business model & roadmap" className="flex flex-col">
      <Title className="mb-[52px]">Open core. Hosted convenience.</Title>
      <ol className="grid grid-cols-3 gap-[56px]">
        {roadmap.map((r, i) => (
          <li key={r.when} className={cn("border-t pt-[24px]", i === 1 ? "border-primary border-t-[6px]" : "border-border")}>
            <Label className="text-foreground">
              <span className="text-accent">{String(i + 1).padStart(2, "0")}</span> / {r.when}
            </Label>
            <h3 className="mt-[14px] font-serif text-[46px] leading-[1.05]">{r.title}</h3>
            <ul className="mt-[20px] space-y-[12px]">
              {r.items.map((it) => (
                <li key={it} className="grid grid-cols-[28px_1fr] text-[23px] leading-[1.4] text-muted-foreground">
                  <span aria-hidden className="font-mono text-accent">
                    ·
                  </span>
                  {it}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
      <div className="mt-auto border border-border bg-card px-[36px] py-[26px]">
        <Label className="mb-[16px]">Revenue</Label>
        <dl className="grid grid-cols-3 gap-[40px]">
          {revenue.map((r) => (
            <div key={r.name}>
              <dt className="flex items-baseline gap-[14px]">
                <span className="font-serif text-[34px]">{r.name}</span>
                <span
                  className={cn(
                    "px-[8px] py-[2px] font-mono text-[13px] uppercase tracking-[0.16em]",
                    r.status === "planned" ? "border border-border text-muted-foreground" : "border border-foreground text-foreground",
                  )}
                >
                  {r.status}
                </span>
              </dt>
              <dd className="mt-[6px] text-[21px] text-muted-foreground">{r.body}</dd>
            </div>
          ))}
        </dl>
      </div>
    </Slide>
  );
}
