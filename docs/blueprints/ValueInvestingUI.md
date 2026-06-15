# Value Investing RAG: Web Frontend & UI Architecture Blueprint

> **📜 HISTORICAL — and the build DIVERGED from it.** This proposed a Streamlit POC
> then a Next.js + Vercel AI SDK + vanilla-CSS app. **None of that is what shipped:**
> the frontend is **Vite + React + TypeScript + Tailwind v4** (no Streamlit, no
> Next.js, no Vercel AI SDK), with a 3-theme system, agent step-timeline,
> insider/smart-money panels, and comparison charts. The split-pane + generative-UI
> + agentic-state *ideas* here did carry through. **For current frontend reality use
> [`../reference/FRONTEND_IMPLEMENTATION.md`](../reference/FRONTEND_IMPLEMENTATION.md).**

## Context for AI Assistant
**Role:** You are acting as a Senior Frontend/Full-Stack Software Engineer assisting with the UI/UX architecture for a custom financial Retrieval-Augmented Generation (RAG) web application.
**Project Goal:** Build a scalable, responsive web interface that allows the user to query complex SEC financial filings, view source citations, and render structured data (tables/charts) alongside conversational AI responses.
**Current State:** The backend RAG architecture (Python, LanceDB, Gemini/Claude models) is already defined. This document outlines the frontend implementation plan, progressing from a local prototype to a decoupled production web app.

---

## 1. The Two-Phase UI Strategy

### Phase 1: The "Proof of Concept" (Streamlit)
Before building a custom React frontend, validate the backend chunking and retrieval logic using a pure Python UI framework.
* **Framework:** **Streamlit** (or Gradio).
* **Why:** It runs completely locally, requires zero HTML/CSS/JavaScript, and integrates natively with your existing Python ingestion script and LanceDB instance. 
* **Goal:** Verify that when you ask about a company's capital expenditures, the correct SEC table is retrieved and the LLM response is accurate. 

### Phase 2: The Production Web App (Decoupled Architecture)
Once the backend logic is flawless, decouple the UI from the Python engine to enable advanced rendering and a modern user experience.
* **Frontend Framework:** **React** (TypeScript) with **Vite**. Using the **Vercel AI SDK** (or similar hooks) for message state management.
* **Backend API Framework:** **FastAPI** (managed by Claude).
* **Styling:** **Vanilla CSS** for custom components, ensuring a data-dense, professional financial dashboard look.

---

## 2. Core UI/UX Features for Financial RAG

A standard ChatGPT-style interface is insufficient for value investing. The UI must be built around verification and data visualization. For the initial prototype, we will focus on the **Visual Components** and **Layout** without full backend integration.

### Feature A: The Split-Pane View (Chat + Source)
* **Left Panel (Chat Interface):** The conversational thread where the user inputs queries and receives the synthesized analysis.
* **Right Panel (Document Viewer):** A dedicated frame that renders the raw HTML or Markdown of the retrieved SEC filing chunk. 

### Feature B: Generative UI (Data Visualization Placeholders)
* **Rendering:** Custom React components for **Recharts** bar graphs and data tables that appear directly inside the chat flow.

### Feature C: Agentic State Indicators
* **Implementation:** A "thought process" dropdown or sidebar status indicator that shows the agent's current step (e.g., *Searching LanceDB...*).

---

## 3. Implementation Plan: API & Frontend

### Step 1: Wrap the Python Engine (FastAPI)
1. Initialize a FastAPI application.
2. Create a `/chat` endpoint that accepts the user's prompt and active conversation history.
3. Wire this endpoint to your existing agentic routing and LanceDB retrieval logic.
4. Ensure the endpoint returns a streaming response (Server-Sent Events) to minimize perceived latency.

### Step 2: Next.js Setup
1. Scaffold a Next.js App Router project.
2. Install `ai` (Vercel AI SDK) to handle message state and streaming natively.
3. Build the core layout: a persistent sidebar for chat history, and the main split-pane content area.

### Step 3: Integrating the Data Visualizations
1. Define strict JSON schemas for your LLM tools (e.g., a `FinancialComparison` schema).
2. Create custom React components (`<BarChartViewer />`, `<RawTableViewer />`) that conditionally render when the Vercel AI SDK streams back structured tool-call data instead of standard text.