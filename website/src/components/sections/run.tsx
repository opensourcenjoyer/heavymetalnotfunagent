"use client";

import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { run, site } from "@/config/site";
import { Section } from "./section";

const TABS = [
  { value: "local", label: "Local", code: run.local },
  { value: "telegram", label: "Bot and site", code: run.telegram },
  { value: "deploy", label: "Fly.io", code: run.deploy },
];

export function Run() {
  const copy = async (code: string) => {
    await navigator.clipboard.writeText(code);
    toast("Copied to clipboard");
  };
  return (
    <Section id="run" index="07" label="Run it" title="Open source. Runs without a model key.">
      <p className="mb-10 max-w-xl text-muted-foreground">
        Wizzy lives inside the heavymetal package. Without an Anthropic key every reading is built from a code template,
        so everything works offline from the model. Payments run on devnet until you switch{" "}
        <code className="font-mono text-sm">WIZZY_X402_NETWORK</code> to mainnet.{" "}
        <a href={site.links.docs} className="link-quiet text-foreground">
          Read WIZZY.md
        </a>
      </p>
      <Tabs defaultValue="local">
        <TabsList className="rounded-none">
          {TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value} className="rounded-none font-mono text-xs">
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {TABS.map((t) => (
          <TabsContent key={t.value} value={t.value} className="relative mt-4">
            <pre className="overflow-x-auto border border-border bg-card p-6 font-mono text-[13px] leading-relaxed">
              {t.code.split("\n").map((line, i, lines) => (
                <span key={line} className="block">
                  <span className="select-none text-muted-foreground">{lines[i - 1]?.endsWith("\\") ? "  " : "$ "}</span>
                  {line}
                </span>
              ))}
            </pre>
            <Button variant="outline" size="sm" onClick={() => copy(t.code)} className="absolute right-3 top-3 rounded-none font-mono text-xs">
              Copy
            </Button>
          </TabsContent>
        ))}
      </Tabs>
    </Section>
  );
}
