# Wizzy website

Landing page for Wizzy ([docs/WIZZY.md](../docs/WIZZY.md)). Next.js static export, shadcn/ui (base-nova), Tailwind v4, bun.

```bash
bun install
bun run dev          # http://localhost:3000
bun run build        # static site in out/, deploy to any static host
bun run lint
```

- Links (Telegram, X, domain) and all page copy live in `src/config/site.ts`.
- `/deck` is the heavymetal pitch deck (copy in `src/config/deck.ts`). Arrows/Space/PgUp/PgDn, Home/End, F for
  fullscreen; the slide number is in the URL hash. PDF: serve `out/`, then
  `google-chrome --headless=new --force-prefers-reduced-motion --no-pdf-header-footer --print-to-pdf=../docs/heavymetal-pitch.pdf http://localhost:<port>/deck.html`.
- The bear is the Braille drawing from `heavymetal/mascot.py`. `src/lib/bear/data.json` and `src/app/icon.svg` are
  generated from it; after changing the mascot run `../.venv/bin/python -I scripts/gen-bear.py`.
- `src/lib/bear/engine.ts` moves individual dots and re-encodes Braille text each frame (dot-field displacement,
  hat ink-fill, the CLI's talking/blink poses). Everything respects `prefers-reduced-motion`.
- UI primitives in `src/components/ui/` are generated with `bunx shadcn@latest add <name>`; prefer regenerating
  them over editing.
