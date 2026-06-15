# PLAN.md: AI Portfolio Impact Analyzer (PoC)

> **💭 SPECULATIVE — NOT built, NOT on the Mosaic roadmap.** This is a separate
> concept exploration (a LangGraph + Neo4j + Groq supply-chain risk analyzer over a
> Schwab CSV) with a different stack from Mosaic. Don't confuse it with the planned
> **watchlist / portfolio view** in `docs/TODO.md`, which would be built in Mosaic's
> own stack (FastAPI + LanceDB + React). Kept as an idea archive only.

## 1. Project Overview
A multi-agent, Directed Acyclic Graph (DAG) workflow that ingests SEC filings and earnings call transcripts, extracts supply chain and operational risks, and maps them to a specific user's portfolio holdings using a Knowledge Graph. 

**Objective:** Build a $0 proof-of-concept (PoC) before exploring paid APIs or scaling.

---

## 2. The $0 Tech Stack
* **Orchestration:** LangGraph (Python)
* **Triage/Fast LLM:** Groq API (Llama 3 / Mixtral) - *Free Tier*
* **Heavy Extraction LLM:** Google AI Studio (Gemini 3.1 Pro) - *Free Tier*
* **Knowledge Graph:** Neo4j AuraDB - *Free Tier (50k nodes max)*
* **Financial Data:** `yfinance` (Python library)
* **SEC Filings:** SEC EDGAR REST API (Direct HTTP requests)
* **User Portfolio:** Local `schwab_holdings.csv` export

---

## 3. Phase 1: Environment & Infrastructure Setup
- [ ] Set up a new Python virtual environment (`venv` or `conda`).
- [ ] Install core dependencies: `pip install langgraph langchain-core langchain-google-genai langchain-groq neo4j yfinance pandas`
- [ ] Generate and store API keys in a `.env` file:
  - `GROQ_API_KEY`
  - `GOOGLE_API_KEY`
  - `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`
- [ ] Create a `schwab_holdings.csv` file with current portfolio tickers and weights.
- [ ] Initialize Neo4j AuraDB Free instance and test the Python driver connection.

---

## 4. Phase 2: Data Ingestion & Graph Seeding
- [ ] **SEC Ingestion Script:** Write a Python function to hit the SEC EDGAR API. 
  - *Crucial:* Include a custom `User-Agent` header (e.g., `Jai_Gupta_Project jai@example.com`) to avoid rate limits/blocks.
- [ ] **Knowledge Graph Seeding (Cypher):**
  - Write a prompt for Gemini to read a standard 10-K "Supply Chain" section and output raw Cypher queries.
  - Manually seed the Neo4j database with 10-20 primary relationships based on the holdings in the CSV (e.g., `(TSMC)-[:SUPPLIES]->(Nvidia)`).

---

## 5. Phase 3: LangGraph Architecture & Nodes
Define the `TypedDict` state schema that will pass between agents (containing the document text, extracted entities, portfolio matches, and the final alert).

### Node 1: The Ingestor (Python)
- Pulls the latest 8-K or 10-Q for a specific test company.
- Cleans HTML/XBRL tags and passes the raw text to the state.

### Node 2: The Triage Agent (Groq / Llama 3)
- **Prompt:** "Read this financial text. Does it contain forward-looking statements about supply chain disruptions, product delays, or macro headwinds? Return strictly True or False."
- **Routing:** If `False`, terminate the graph. If `True`, route to Node 3.

### Node 3: The Deep Analyst (Gemini)
- **Prompt:** "Extract specific risk vectors and the exact companies/components mentioned. Format as a JSON list of entities."
- Updates the state with the extracted entities.

### Node 4: The Graph Synthesizer (Python + Neo4j)
- Takes the entities from Node 3 and runs a Cypher query against AuraDB.
- Checks if the extracted entity is $\leq$ 2 hops away from any ticker in `schwab_holdings.csv`.
- Updates the state with the portfolio intersection.

### Node 5: The Output Formatter (Python)
- Takes the portfolio intersection and the original Gemini summary.
- Formats a clean markdown alert (e.g., "🚨 **Impact Alert:** Your holding in [Ticker] may be affected by an aluminum shortage reported by Alcoa...").
- Prints to the terminal or sends a webhook to a private Discord/Slack channel.

---

## 6. Phase 4: Testing & Iteration
- [ ] Run the pipeline on historical data: Feed it an old 10-K where you already know a supply chain shock occurred.
- [ ] Check token usage on Google AI Studio to ensure the context windows are being managed efficiently.
- [ ] Refine the Cypher queries to handle edge cases (e.g., subsidiaries).