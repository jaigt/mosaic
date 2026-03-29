# Value Investing RAG: Frontend Implementation Reference

> **Status (2026-03-29):** Fully integrated with backend. No longer a visual prototype — all API calls are live. Bug fixes applied to sidebar polling, ingest modal async flow, split-pane resizing, and SEC table layout.

## 1. Project Architecture

- **Framework:** React 18 (TypeScript)
- **Build Tool:** Vite 5
- **Styling:** Vanilla CSS + CSS Variables (Bloomberg-style dark theme)
- **Icons:** Lucide React
- **Data Visualization:** Recharts
- **Backend:** FastAPI at `http://localhost:8000`, proxied via Vite (`/api/*`)

## 2. Component Structure (`frontend/src/components/`)

### Core Layout
- **`App.tsx`**: Global state owner. Holds `sources: Source[]` and `activeFiling: FilingInfo | null`. Manages resizable split-pane (2% to 98%); both panel wrappers have `minWidth: 0; overflow: hidden` so panels can shrink freely at any size.
- **`Sidebar.tsx`**: Navigation + **Ingested Filings List**. Shows status for background ingestion and provides a **Re-ingest/Refresh** button for each document.

### Chat Interface (Left Panel)
- **`ChatPanel.tsx`**: SSE streaming logic. Managed "Filing Mode" when a document is selected in the sidebar, passing explicit filters (`ticker`, `year`, `doc_type`) to the backend.
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

## 5. Visual Identity (CSS Variables in `src/index.css`)

| Variable | Value | Use |
|---|---|---|
| `--bg-primary` | `#0a0e14` | Main background |
| `--bg-secondary` | `#141920` | Panel backgrounds |
| `--bg-sidebar` | `#0d1117` | Sidebar |
| `--accent-color` | `#007bff` | Buttons, highlights |
| `--success-color` | `#28a745` | Completed steps, source badges |
| `--border-color` | `#21262d` | Dividers |
| `--text-primary` | `#e6edf3` | Main text |
| `--text-secondary` | `#7d8590` | Labels, captions |

## 6. SEC Table Rendering

Tables are stored as cleaned HTML. The frontend applies specialized CSS in `SourcePanel.tsx`:
- `vertical-align: bottom` for headers.
- `text-align: center` for header cells (date labels), `text-align: right` for `tbody` numeric data.
- `text-align: left` for the first column (line items) in both `thead` and `tbody`.
- **Empty spacer cells** (`td:empty`, `th:empty`) collapsed to ~4px width — SEC filings use bare `<td></td>` cells as column spacers; without this, merged `$` cells leave large gaps between data columns.
- `overflow-x: auto` on the container so wide tables scroll rather than overflow the panel.
