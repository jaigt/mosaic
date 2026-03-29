# Value Investing RAG: Frontend Implementation Reference

This document provides a technical overview of the React-based visual prototype built for the Value Investing RAG application.

## 1. Project Architecture
- **Framework:** React 18 (TypeScript)
- **Build Tool:** Vite
- **Styling:** Vanilla CSS + CSS Variables (Bloomberg-esque Financial Theme)
- **Icons:** Lucide React
- **Data Visualization:** Recharts

## 2. Component Structure (`frontend/src/components/`)

### Core Layout
- **`App.tsx`**: Manages the global layout, including the sidebar and a custom-built resizable split-pane system. It uses percentage-based widths to ensure responsiveness between the Chat and Source panels.
- **`Sidebar.tsx`**: Provides navigation and high-level application controls (Dashboard, History, Settings).

### Chat Interface (Left Panel)
- **`ChatPanel.tsx`**: The main container for the conversational flow. It handles the message list and the input area with support for file uploads.
- **`Message.tsx`**: A polymorphic component that renders:
    - Standard text responses.
    - **Generative UI:** Embedded financial charts based on JSON payloads.
    - **Citations:** Interactive badges that link the analysis to specific document sections.
- **`AgentState.tsx`**: An expandable "Thought Process" indicator that provides transparency into the RAG pipeline's internal steps (e.g., "Filtering LanceDB", "Synthesizing tables").

### Source Viewer (Right Panel)
- **`SourcePanel.tsx`**: A high-fidelity document viewer designed for SEC filings. It features:
    - Tabbed navigation for multiple documents.
    - Financial table rendering with professional formatting.
    - "Citation Highlighting" simulation (using `<mark>` tags) to show where the AI extracted data.

### Data Visualization
- **`Visualizer/FinancialChart.tsx`**: A reusable Recharts-based bar chart component configured for financial metrics (e.g., Revenue growth, R&D spend).

## 3. Visual Identity (CSS Variables)
Defined in `src/index.css`:
- **Primary BG:** `#0a0e14` (Deep Navy/Black)
- **Accent:** `#007bff` (Professional Blue)
- **Success:** `#28a745` (Financial Green)
- **Font:** Inter for UI, JetBrains Mono for data/tables.

## 4. Integration Roadmap (Phase 2)
When merging with the Python/FastAPI backend, follow these steps:

1.  **Vercel AI SDK:** Replace the local `useState` messages in `ChatPanel.tsx` with the `useChat` hook from the Vercel AI SDK.
2.  **Streaming Tool Calls:** Update `Message.tsx` to detect `tool_calls` from the LLM. When the backend returns a `generate_chart` tool call, pass the JSON arguments directly to `FinancialChart.tsx`.
3.  **Source Linking:** Implement a `postMessage` or shared state bridge between the `Message` citations and the `SourcePanel` scroll position to enable "click-to-verify" functionality.
4.  **Real-time Steps:** Connect `AgentState.tsx` to a WebSocket or Server-Sent Events (SSE) stream from the FastAPI agent to show live progress updates.

## 5. Development
To run the prototype:
```bash
cd frontend
npm install
npm run dev
```