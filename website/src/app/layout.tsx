import type { Metadata } from "next";
import { Instrument_Serif, Inter, JetBrains_Mono, Noto_Sans_Symbols_2 } from "next/font/google";

import { Toaster } from "@/components/ui/sonner";
import { site } from "@/config/site";
import { cn } from "@/lib/utils";
import "./globals.css";

const sans = Inter({ variable: "--font-inter", subsets: ["latin"] });
const serif = Instrument_Serif({ variable: "--font-instrument", subsets: ["latin"], weight: "400" });
const mono = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"] });
// Braille Patterns block for the bear: most mono fonts lack it or give it a different advance width.
const braille = Noto_Sans_Symbols_2({ variable: "--font-braille", subsets: ["braille", "symbols"], weight: "400" });

export const metadata: Metadata = {
  metadataBase: new URL(site.url),
  title: site.title,
  description: site.description,
  openGraph: { title: site.title, description: site.description, url: site.url, siteName: site.name, type: "website" },
  twitter: { card: "summary_large_image", title: site.title, description: site.description },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={cn("antialiased", sans.variable, serif.variable, mono.variable, braille.variable)}>
      <body className="min-h-dvh bg-background font-sans text-foreground">
        {children}
        <Toaster position="bottom-left" theme="light" />
      </body>
    </html>
  );
}
