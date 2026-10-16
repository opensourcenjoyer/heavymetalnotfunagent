import { Craft } from "@/components/sections/craft";
import { Hero } from "@/components/sections/hero";
import { Next } from "@/components/sections/next";
import { Prophecies } from "@/components/sections/prophecies";
import { Readings } from "@/components/sections/readings";
import { Run } from "@/components/sections/run";
import { Safety } from "@/components/sections/safety";
import { SiteFooter } from "@/components/sections/site-footer";
import { SiteHeader } from "@/components/sections/site-header";
import { Tarot } from "@/components/sections/tarot";

export default function Home() {
  return (
    <>
      <SiteHeader />
      <main>
        <Hero />
        <Readings />
        <Craft />
        <Tarot />
        <Prophecies />
        <Safety />
        <Next />
        <Run />
      </main>
      <SiteFooter />
    </>
  );
}
