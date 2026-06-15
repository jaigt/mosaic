# Mosaic: Frontend Implementation Reference

> **Last updated:** 2026-06-15 (3-theme system, agent-event UI, insider/smart-money
> panels, manual-ingest removed, comparison charts, chat persistence).
> Tailwind v4 + a reusable `ui/` primitives library. For open work see
> [`../TODO.md`](../TODO.md); for current state see
> [`../PROJECT_STATUS_AND_ROADMAP.md`](../PROJECT_STATUS_AND_ROADMAP.md).

## 1. Project Architecture

- **Framework:** React 18 (TypeScript)
- **Build Tool:** Vite 5
- **Styling:** Tailwind CSS v4 (CSS-first, `@theme` tokens in `index.css`) + a
  `ui/` primitives library. No `tailwind.config.js`/PostCSS — uses the
  `@tailwindcss/vite` plugin.
- **Icons:** Lucide React
- **Data Visualization:** Recharts
- **HTML sanitization:** DOMPurify (SEC table HTML before `dangerouslySetInnerHTML`)
- **Tests:** Vitest + React Testing Library (`npm test`)
- **Backend:** FastAPI at `http://localhost:8000`, proxied via Vite (`/api/*`)

## 2. Component Structure (`frontend/src/components/`)

### Core Layout
- **`App.tsx`**: Global state owner — `sources`, `activeFiling`, theme, and the
  derived `activeTicker` (`dominantTicker(sources)`, falling back to the focused
  filing) that drives the sidebar panels. Resizable split-pane (chat-dominant
  default); responsive — below the `md` breakpoint the sidebar becomes an overlay
  drawer and panels stack (`useMediaQuery`). App-root `ErrorBoundary`.
- **`Sidebar.tsx`**: Brand masthead + **filing ledger** (click a filing to focus
  chat on it) + the **InsiderPanel** and **SmartMoneyPanel** (keyed to
  `activeTicker`). *No manual-ingest button* — the agent ingests on demand.

### UI primitives (`frontend/src/components/ui/`)
Typed, accessible building blocks: `Button`, `Input`/`Textarea`, `Select`, `Modal`
(focus trap, Esc/backdrop close), `Badge`, `Card`, `Spinner`, `cn`. Vitest-tested.

### Chat Interface
- **`ChatPanel.tsx`**: SSE streaming with `AbortController` (Stop button);
  capability-showcasing empty-state prompts; chat persisted to `localStorage`;
  hosts the **`ThemeToggle`** (Study / Light / Dark). Passes explicit filters when
  a filing is focused.
- **`Message.tsx`**: `react-markdown` (lazy) + the `<chart>` generative-UI parser +
  a **verification badge** (Verified / N-to-verify / Not-verified) + clickable
  source pills.
- **`AgentState.tsx`**: live step timeline driven by SSE `status` **and**
  `agent_step` events (search / ingest / insider / smart-money), with kind-based
  styling.
- **`ThemeToggle.tsx`** (+ `hooks/useTheme.ts`): 3-way theme switch, persisted.

### Sidebar data panels
- **`InsiderPanel.tsx`**: Form 4 buy/sell sentiment + transactions for the active
  ticker (`/insiders/{ticker}`).
- **`SmartMoneyPanel.tsx`**: which curated superinvestors hold the active ticker,
  position size + Q/Q change (`/smart-money/{ticker}`).

### Source Viewer (Right Panel)
- **`SourcePanel.tsx`**: retrieved SEC chunks as "paper exhibit" tabs (themed —
  Study renders them as ivory sheets; modern themes as clean cards). Specialized
  SEC-table CSS (see §6).

### Data Visualization
- **`Visualizer/FinancialChart.tsx`** (lazy-loaded): Recharts **bar / line / area**,
  single- or **multi-series** (comparison charts). `resolveSeries()` infers series
  from the `<chart>` spec; colors are theme tokens.

## 3. Generative UI (Charts)

The system supports embedding interactive charts directly in the chat.
- **Trigger:** The synthesis LLM outputs a JSON block wrapped in `<chart>` tags.
- **Format:** `type` (`bar`|`line`|`area`, default bar) + `data`; single-series uses
  a `value` key, multi-series uses one key per series plus an optional `series` list:
  ```json
  <chart>
  { "type": "line", "title": "Revenue ($B)",
    "data": [ {"name": "2023", "AAPL": 383.3, "MSFT": 211.9} ],
    "series": ["AAPL", "MSFT"] }
  </chart>
  ```
- **Rendering:** `Message.tsx` parses the tag; `FinancialChart` resolves the series
  (back-compatible with the legacy `{name, value}` shape) and renders inline.

## 4. Ingestion — fully agentic (no manual UI)

There is **no ingest button/modal**. When you ask about a company the corpus
doesn't have, the **agent auto-ingests** its filing from EDGAR mid-answer
(surfaced as `agent_step` events in the chat timeline) and re-searches. The
filing ledger fills as the agent fetches. (`POST /api/ingest` still exists as a
programmatic path but nothing in the UI calls it.)

## 5. Visual Identity — 3 themes (`@theme` + `html[data-theme]` in `src/index.css`)

Tokens are semantic and stable (`amber-*` = "the accent", `ink-*` = "the surface
scale", `fg-*`/`paper-*` = text), consumed as Tailwind utilities. **Three themes
share the same component code** — the `@theme` block holds the default **Study**
values, and `html[data-theme="modern-dark"|"modern-light"]` blocks redefine the
same variables (see `VISUAL_AUDIT.md`):

- **Study** (default) — engraved-ledger: racing-green ink, brass-gold foil accent,
  serif display, grain/guilloche/lamp-glow atmosphere, ivory "paper" source sheets.
- **Modern-Dark** — sleek neutral near-black, electric-blue accent, grotesk type, flat.
- **Modern-Light** — clean white/soft-gray, electric-blue accent, grotesk type.

The toggle (`ThemeToggle`) persists to `localStorage['vr.theme']` with a no-flash
inline init in `index.html`. Per-theme overrides neutralize the Study-only
atmosphere (`body`, `.vr-foil`, `.vr-paper`) and swap fonts; `--color-on-accent`
keeps primary-button text readable on each accent. The table below describes the
**Study** token values:

| Token family | Examples | Use |
|---|---|---|
| `ink-*` (950→500) | `#090e0b`→`#2b4030` | Backgrounds / surfaces (deep racing-green ink) |
| `line*` | `line`, `line-strong`, `line-soft` | Hairlines / borders (certificate rules) |
| `paper-*` / `fg-*` | `#f1ecdc`, `#e9e6d7`→`#66745f` | Headings / body / muted text (ivory) |
| `amber-*` (200→600) | `#f1e2ae`→`#8a6c27` | Brass-gold accent (foil buttons, tickers, seals) |
| `ledger-*` | `#99dfb0`→`#25754c` | Positive / source signals (mint) |
| `crimson-*` / `azure-*` | `#dd7158`, `#6fa6cf` | Negative / info signals (oxblood / steel) |
| `--paper-*` (`:root` vars) | `--paper-bg #f3eedf`, `--paper-ink #232a22` | The light "paper document" palette used by `.vr-paper` |

Fonts (loaded in `index.html`): **Gloock** (didone display — headlines, seals),
**Newsreader** (filing prose + editorial italics), **Hanken Grotesk** (UI),
**Spline Sans Mono** (tickers/figures, tabular-nums). Legacy `--bg-*`/`--accent-*`
variables are aliased to the palette for backward compatibility.

Signature pieces (all in `index.css`):
- **`.vr-paper`** — sources render as ivory paper sheets ("exhibits") inside the
  dark UI; `.vr-paper .sec-table-container` flips the SEC table styles to a
  print palette. Used by `SourcePanel`'s `SourceChunkView`.
- **`.vr-foil`** — gold-foil gradient + hover sheen sweep; `Button[variant=primary]`.
- **`.vr-rule-b` / `.vr-rule-t`** — double hairline rules (certificate borders)
  for panel headers/footers.
- **`.vr-leader`** — dotted ledger leaders (`AAPL ····· 2026 10-Q`) in the sidebar.
- Body background layers grain + guilloche arcs + lamp-glow vignette.

> ⚠️ **Do not add an un-layered `* { margin:0; padding:0 }` reset.** Tailwind v4
> emits utilities inside `@layer utilities`; un-layered author CSS out-cascades
> every layer, silently zeroing all spacing utilities app-wide (this bug shipped
> once — removed 2026-06-09). Preflight already handles resets.

## 6. SEC Table Rendering

Tables are stored as cleaned HTML, sanitized with DOMPurify, then rendered. The
specialized table CSS lives in `src/index.css` under `.sec-table-container`
(moved out of `SourcePanel.tsx`):
- `vertical-align: bottom` for headers.
- `text-align: center` for header cells (date labels), `text-align: right` for `tbody` numeric data.
- `text-align: left` for the first column (line items) in both `thead` and `tbody`.
- **Empty spacer cells** (`td:empty`, `th:empty`) collapsed to ~4px width — SEC filings use bare `<td></td>` cells as column spacers; without this, merged `$` cells leave large gaps between data columns.
- `overflow-x: auto` on the container so wide tables scroll rather than overflow the panel.
