import type { Metadata } from "next";

import { Deck } from "@/components/deck/deck";
import { deck } from "@/config/deck";
import "./deck.css";

export const metadata: Metadata = {
  title: deck.title,
  description: "heavymetal: an open-source AI agent for Solana memecoins, and Wizzy, its read-only wizard bear.",
  robots: { index: false },
};

export default function DeckPage() {
  return <Deck />;
}
