# Value Investing RAG: System Architecture Blueprint

> **📜 HISTORICAL — the original (pre-build) backend blueprint.** The architecture
> here (LanceDB, two-pass table summarization, metadata pre-filter + vector search,
> multi-provider routing, the `DocumentChunk` schema) is essentially what shipped.
> BUT specifics are out of date: model names (`Gemini 3.1 Pro`, `text-embedding-004`)
> are NOT what's used (synthesis = `gemini-2.5-flash`, embeddings = local
> `bge-large`), and `chunk_type` is `text`/`table` only. **For current backend
> reality use [`../reference/BACKEND.md`](../reference/BACKEND.md) and
> [`../PROJECT_STATUS_AND_ROADMAP.md`](../PROJECT_STATUS_AND_ROADMAP.md).**

## Context for AI Assistant
**Role:** You are acting as a Senior AI Software Engineer assisting with the development of a custom Retrieval-Augmented Generation (RAG) pipeline for value investing.
**Project Goal:** Build a local, lightweight system capable of parsing, chunking, and reasoning over complex SEC financial filings (10-Ks, 10-Qs) to outperform generic document-chat interfaces.
**Current State:** The architectural blueprint is finalized. We are moving into the implementation phase. Please adhere to the tech stack and design philosophies outlined below. Do not suggest migrating to heavy cloud vector databases unless explicitly requested.

---

## 1. Tech Stack & Model Selection

### Core Infrastructure (Local)
* **Language:** Python
* **Vector Database:** **LanceDB** (Open-source, runs locally on disk, excels at combining vector search with strict SQL-like metadata filtering).
* **Data Sourcing:** `edgartools` (Python library for the SEC EDGAR API).
* **Document Parsing:** **Unstructured.io** or **LlamaParse** (Layout-aware parsers capable of extracting complex HTML/XBRL tables).

### LLM Strategy (The Multi-Model Approach)
* **The Heavy Lifter (Routing & Final Synthesis):** **Gemini 3.1 Pro** or **Claude 3.7 Sonnet**. Used for final user-facing generation, complex reasoning, and synthesizing retrieved chunks.
* **The Fast Workhorse (Data Pipeline & Table Summarization):** **Gemini Flash** or **Claude 3 Haiku**. Used during ingestion to convert every financial table into a semantic summary. 
* **The Embedding Model:** Google's **`text-embedding-004`** or OpenAI's **`text-embedding-3-small`**. 

---

## 2. Metadata Schema Design (Pydantic)
Every chunk embedded into LanceDB must adhere to this strict structure to ensure highly accurate filtering prior to vector search:

```python
from pydantic import BaseModel, Field
from typing import Literal

class DocumentChunk(BaseModel):
    chunk_id: str
    ticker: str = Field(..., description="Stock ticker symbol, e.g., AAPL")
    cik: str = Field(..., description="SEC CIK number")
    document_type: Literal["10-K", "10-Q", "8-K"]
    filing_year: int
    filing_quarter: Literal["Q1", "Q2", "Q3", "Q4", "FY"]
    sec_item_section: str = Field(..., description="e.g., 'Item 7: MD&A'")
    chunk_type: Literal["text", "table", "chart"]
    text_content: str = Field(..., description="The actual text or LLM-generated table summary to be embedded")
    raw_payload: str = Field(..., description="The raw HTML/Markdown of the table, or the raw text snippet")
```

---

## 3. Implementation Plan: Phase by Phase

### Phase 1: Ingestion & Layout Parsing
1. **Fetch:** Use `edgartools` to pull the raw HTML of target 10-Ks. (Ensure `User-Agent` complies with SEC rate limits).
2. **Parse:** Run HTML through Unstructured.io to separate the document into distinct elements (Headers, NarrativeText, Tables).
3. **Group by Section:** Track headers (e.g., "Item 1A. Risk Factors") and assign that metadata tag to all subsequent elements until the next major header.

### Phase 2: The Two-Pass Table Strategy (Crucial)
1. **Isolate:** When the parser hits a `Table` element, isolate the raw HTML or Markdown.
2. **Summarize:** Send the raw table to the Fast Workhorse model (Flash/Haiku) with the prompt: *"You are a financial analyst. Summarize the following SEC financial table. State the key metrics, notable YoY changes, and clear trends. Output ONLY the summary."*
3. **Package:** Store the LLM's text summary in the `text_content` field (for vectorization), and store the raw table in the `raw_payload` field (for retrieval and final synthesis).

### Phase 3: Embedding & Storage
1. **Batch:** Group parsed chunks (narrative text and table summaries) into batches.
2. **Embed:** Send `text_content` to the embedding model.
3. **Upsert:** Save the vectors and Pydantic metadata into the local LanceDB instance. 

### Phase 4: Retrieval & Agentic Routing
1. **Query Parsing:** Use a fast LLM to extract metadata filters from the user's prompt (e.g., `{ticker: "MSFT", year: 2024}`).
2. **Pre-Filtering:** Query LanceDB to isolate only the vectors matching those tags.
3. **Vector Search:** Perform semantic search on the filtered subset.
4. **Synthesis:** Pass the user's query and the retrieved `raw_payload` data to the Heavy Lifter model (Pro/Sonnet) to generate the final analysis.
```