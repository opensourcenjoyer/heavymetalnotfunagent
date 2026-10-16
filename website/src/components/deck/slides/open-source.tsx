import { openSource } from "@/config/deck";
import { Lead, Slide, type SlideProps, Title } from "../slide";

export function OpenSource(p: SlideProps) {
  const [, closed, ours] = openSource.headers;
  return (
    <Slide {...p} label="Why open source">
      <div className="grid grid-cols-12 items-end gap-[64px]">
        <Title className="col-span-7 text-[96px] leading-[0.98]">
          Open source is the only way to build <span className="bg-primary px-[12px]">trust</span>.
        </Title>
        <Lead className="col-span-5 pb-[8px]">
          An agent that holds your keys has to be verifiable. You should be able to read it before you fund it.
        </Lead>
      </div>
      <table className="mt-[52px] w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-foreground font-mono text-[17px] uppercase tracking-[0.2em] text-muted-foreground">
            <th className="w-[300px] pb-[14px] font-normal" />
            <th className="w-[560px] pb-[14px] font-normal">{closed}</th>
            <th className="pb-[14px] font-normal text-foreground">
              {ours}
              <span className="text-primary">.</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {openSource.rows.map(([k, a, b]) => (
            <tr key={k} className="border-b border-border">
              <th scope="row" className="py-[16px] font-mono text-[18px] font-normal uppercase tracking-[0.16em]">
                {k}
              </th>
              <td className="py-[16px] text-[25px] text-muted-foreground">{a}</td>
              <td className="py-[16px] text-[25px]">
                <span aria-hidden className="mr-[14px] font-mono text-secondary">
                  █
                </span>
                {b}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Slide>
  );
}
