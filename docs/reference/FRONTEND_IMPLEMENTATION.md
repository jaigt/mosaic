# Value Investing RAG: Frontend Implementation Reference

> **Last updated:** 2026-06-02. Fully integrated with backend; all API calls live.
> Now on a Tailwind v4 design system with a reusable `ui/` primitives library.
> For open frontend work see [`../TODO.md`](../TODO.md).

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
- **`App.tsx`**: Global state owner. Holds `sources: Source[]` and `activeFiling: FilingInfo | null`. Manages resizable split-pane (2% to 98%); both panel wrappers have `minWidth: 0; overflow: hidden` so panels can shrink freely at any size.
- **`Sidebar.tsx`**: Navigation + **Ingested Filings List**. Shows status for background ingestion and provides a **Re-ingest/Refresh** button for each document.

### UI primitives (`frontend/src/components/ui/`)
Typed, accessible building blocks used across the app: `Button`, `Input`/`Textarea`,
`Select`, `Modal` (focus management, Esc/backdrop close), `Badge`, `Card`, `Spinner`,
plus a `cn` class-merge helper. Smoke-tested with Vitest.

### Chat Interface (Left Panel)
- **`ChatPanel.tsx`**: SSE streaming logic with an `AbortController` (Stop button
  cancels an in-flight stream). "Filing Mode" when a document is selected in the
  sidebar, passing explicit filters (`ticker`, `year`, `doc_type`) to the backend.
- **`Message.tsx`**: Renders messages via `react-markdown`. Includes a **Generative UI parser** for `<chart>` tags. Renders source badges from retrieved chunks.
- **`AgentState.tsx`**: Live "thought process" indicator driven by real SSE `status` events.
- **`IngestModal.tsx`**: Form for new filings. Uses the background task system with polling to prevent UI timeouts.

### Source Viewer (Right Panel)
- **`SourcePanel.tsx`**: Displays real retrieved SEC chunks as tabs. 
  - **Visual Identity**: Professional GitHub-style dark theme (`#0d1117`).
  - **Table Rendering**: Specialized CSS for SEC tables with hover states, numeric right-alignment, and header detection. Preserves empty `<td>` cells for proper layout.
  - **AI Context**: Blue callout boxes above tables provide LLM-generated summaries.

### Data Visualization
- **`Visualizer/FinancialChart.tsx`**: Recharts bar chart for financial metrics. Embedded in `Message.tsx` when the LLM triggers a `<chart>` tag.

## 3. Generative UI (Charts)

The system supports embedding interactive charts directly in the chat.
- **Trigger:** The synthesis LLM outputs a JSON block wrapped in `<chart>` tags.
- **Format:**
  ```json
  <chart>
  {
    "title": "Revenue Comparison",
    "data": [
      {"name": "2022", "value": 117.1},
      {"name": "2023", "value": 125.4}
    ]
  }
  </chart>
  ```
- **Rendering:** `Message.tsx` parses this tag, extracts the data, and renders the `FinancialChart` component inline.

## 4. Background Ingestion Flow

To handle long SEC processing times, ingestion is asynchronous:
1. **Trigger:** User clicks "Ingest" or "Refresh". Frontend calls `POST /api/ingest`.
2. **Response:** Backend returns `task_id` immediately.
3. **Polling:** Frontend `IngestModal` or `Sidebar` polls `GET /api/ingest/status/{task_id}` every 2.5s.
4. **Completion:** When status is `completed`, the UI updates the chunk count and refreshes the filings list.

## 5. Visual Identity — "Ledger Terminal" tokens (`@theme` in `src/index.css`)

Design tokens are defined once in the `@theme` block and consumed as Tailwind
utility classes (e.g. `bg-ink-900`, `text-fg-100`, `border-line`, `text-amber-400`).

| Token family | Examples | Use |
|---|---|---|
| `ink-*` (950→500) | `#07090d`→`#28323f` | Backgrounds / surfaces (deep cool near-black) |
| `line*` | `line`, `line-strong`, `line-soft` | Dividers / borders |
| `paper-*` / `fg-*` | `#f4f1e9`, `#e8ebf0`→`#5e6877` | Headings / body / muted text |
| `amber-*` (300→600) | `#f3c969`→`#a86f16` | Primary accent (tickers, highlights) |
| `ledger-*` | `#7fdca4`→`#1d7a4f` | Positive / source signals (green) |
| `crimson-*` / `azure-*` | `#e8675f`, `#5aa9e8` | Negative / info signals |

Fonts (loaded in `index.html`): **Fraunces** (display), **Newsreader** (filing prose),
**IBM Plex Sans** (UI), **IBM Plex Mono** (tickers/figures). Legacy `--bg-*`/`--accent-*`
variables are aliased to the new palette for backward compatibility.

## 6. SEC Table Rendering

Tables are stored as cleaned HTML, sanitized with DOMPurify, then rendered. The
specialized table CSS lives in `src/index.css` under `.sec-table-container`
(moved out of `SourcePanel.tsx`):
- `vertical-align: bottom` for headers.
- `text-align: center` for header cells (date labels), `text-align: right` for `tbody` numeric data.
- `text-align: left` for the first column (line items) in both `thead` and `tbody`.
- **Empty spacer cells** (`td:empty`, `th:empty`) collapsed to ~4px width — SEC filings use bare `<td></td>` cells as column spacers; without this, merged `$` cells leave large gaps between data columns.
- `overflow-x: auto` on the container so wide tables scroll rather than overflow the panel.
