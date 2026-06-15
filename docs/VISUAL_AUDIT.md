# Visual Design Audit — Value Investing RAG (2026-06-15)

Grounded in screenshots of the running app (desktop, populated panels, mobile),
not code-reading. Companion to `docs/UX_AUDIT.md` (which covered interaction /
discoverability, not the look).

## Verdict

The **aesthetic direction is a genuine asset** and was kept: the "Analyst's
Study" identity (editorial serif display, brass-gold foil accents on racing-green
ink, ledger/"exhibits" metaphors) reads as a serious, premium finance instrument
— not a generic chatbot. The problems were execution details, now addressed, plus
a request for an alternative modern look.

## Issues found → resolution

| # | Issue (from screenshots) | Resolution |
|---|---|---|
| 1 | **Contrast/legibility** — many ~9–10px dim mono labels (sidebar headers, "excerpts indexed", footer, composer hint, prompt tags) low-contrast on near-black; likely sub-AA. | Bumped study's dimmest text tokens (`fg-300`/`fg-400`); the new modern palettes are AA-tuned. |
| 2 | **Mobile header overflow** — focused-filing badge ("AAPL 2023 10-K ✕") clipped at 375px. | Badge constrained (`max-w-[42vw]`, truncate, ✕ kept reachable). |
| 3 | **Suggested prompts below the fold** on short/mobile — discoverability prompts cut off. | Empty-state area scrolls (`min-h-full`) so prompts are always reachable. |
| 4 | **Insider rows lost info** — names truncated to initials, dates wrapped, fund names hard-truncated. | Insider name on its own truncating line (+`title`); compact single-line date; tooltips on fund names. |

## Themes (delivered)

A 3-theme system, toggle in the chat header (Study / Light / Dark), persisted to
`localStorage['vr.theme']` (no-flash inline init in `index.html`). Mechanism:
Tailwind v4 `@theme` vars are the **study** defaults; `html[data-theme="…"]`
blocks redefine the same variables, so components are unchanged.

- **Study** (default) — editorial racing-green + brass-gold, serif display, grain/
  guilloche/lamp-glow atmosphere. Unchanged except the legibility bump.
- **Modern-Dark** — sleek neutral near-black (Linear/Vercel), **electric-blue**
  accent, grotesk type, flat (atmosphere neutralized).
- **Modern-Light** — clean white/soft-gray (Stripe-light), electric-blue accent,
  grotesk type, high-contrast dark text.

Per-theme the hardcoded bits were neutralized: `body` atmosphere → flat themed
bg for modern; `.vr-foil` gold→flat blue (+`--color-on-accent` so primary-button
text stays readable: dark on gold / white on blue); `.vr-paper` grain dropped for
modern source cards.

## Not changed (taste, left as-is)

The palette energy: gold is used sparingly in Study (deliberately restrained). If
more "pop" is wanted later, let positive/negative signals (net-buying green) carry
a touch more weight — but the restraint suits the "serious analyst" voice.

## Verified

Screenshotted all three themes (desktop + populated insider/smart-money panels)
and mobile; study confirmed visually identical to before. `npm run build` clean,
57 Vitest tests pass.
