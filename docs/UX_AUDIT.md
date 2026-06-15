# UX Audit — Value Investing RAG (2026-06-15)

An end-to-end audit of how a user navigates and uses what we've built, after the
agentic upgrades (auto-ingest, ReAct tools, insider/13F/smart-money trackers,
comparison charts, self-verification).

## The core tension (read this first)

We built an **autonomous analyst** — it fetches missing filings on demand, pulls
insider/institutional/smart-money data, compares across companies, charts, and
verifies its own numbers. But the UI still presents like a **"ingest a filing,
then query it"** tool. **The single biggest UX problem is discoverability:
users won't know what they can ask.** The capability is agentic; the interface
isn't advertising it. Most of the highest-leverage fixes are *copy and
surfacing*, not new features.

---

## Findings, prioritized

### P0 — Make the agent's powers discoverable (highest leverage, low effort)

1. **Empty-state copy undersells the agent.** It reads *"Pick a filing from the
   ledger or ingest a new one, then ask."* That directly contradicts auto-ingest
   and trains users to think they must ingest first. → Reframe to **"Ask about
   any company — I'll pull its filings myself."**
2. **Suggested prompts are generic** (risk factors / revenue / chart) and
   showcase none of the new powers. A user has no way to discover they can ask:
   - "How did **Microsoft** do last quarter?" (auto-ingest a name not in corpus)
   - "**Compare** AAPL, MSFT and GOOGL revenue" (multi-company + comparison chart)
   - "Which **superinvestors** own NVDA?" (smart-money tool)
   - "Any **insider buying** at TSLA?" (Form 4 tool)
   → Replace the 3 static prompts with capability-showcasing ones (ideally a
   labeled set so the *category* of power is visible).
3. **The composer placeholder + hint** ("Ask the filings — margins, risks,
   guidance…") reinforce the narrow framing. → Widen to invite company names,
   comparisons, and ownership questions.

### P1 — Surfacing the trackers & sources

4. **Insider / Smart-money panels only appear when a filing is focused**
   (`activeFiling`). A first-time user with an empty corpus never sees them and
   never learns they exist. → Show a teaser/empty state for them, and/or key
   them to the **last ticker discussed in chat**, not just a focused filing.
5. **The panels and the chat tools are redundant but disconnected.** The same
   insider/smart-money data is both a sidebar panel and a chat tool — good — but
   nothing tells the user "you can also just *ask* about this." A one-line hint
   linking the two would close the loop.
6. **Manual "Ingest" is still a primary CTA** (button in header + composer +
   sidebar). Given auto-ingest, it should be a *power-user* affordance, not the
   front door. De-emphasize it; lead with "just ask."

### P1 — Onboarding / first run

7. **No onboarding.** A new user lands on an empty desk with only the hero +
   prompts. Fixing P0 (prompts + copy) largely covers this; a subtle one-time
   "what this analyst can do" affordance would seal it.
8. **Smart-money index is empty until the first refresh.** Now auto-refreshed on
   startup, but the very first run shows "index not built" briefly. The panel
   handles it gracefully; acceptable.

### P2 — Clarity & polish

9. **Verification badge** ("Verified against sources" / "N points to verify") is
   a strong trust signal but unexplained. → Add a tooltip: "Every figure was
   re-checked against the cited filings."
10. **Layout is 50/50 chat vs sources.** For a chat-first agent, consider making
    chat the dominant panel with sources collapsible/secondary (the source panel
    is most useful *after* an answer, via citation clicks).
11. **No chat persistence.** Messages are in-memory; a refresh wipes the
    conversation. Consider localStorage persistence. (Out of current scope.)
12. **Agent-step timeline** (search/ingest/verify) is good transparency — keep
    it; it's how users *learn* the agent is doing multi-step work.

---

## What's already agentic/callable (the plumbing exists)

The user can already, *just by chatting*, trigger: corpus search, **auto-ingest
of a missing filing**, **insider activity**, **fund holdings (13F)**,
**which superinvestors hold a ticker**, **cross-company comparison + chart**, and
**answer self-verification**. The gap is **telling them** — not building more.

### Genuinely not built (future, if wanted)
- Catalysts / earnings-date awareness, news, price data, alerts/watchlists.
- "Funds holding X" beyond the curated superinvestor set.

---

## Recommended actions (in order)

| # | Action | Effort | Leverage |
|---|---|---|---|
| 1 | Reframe empty-state hero/subcopy to "ask about any company, I'll fetch it" | XS | ★★★ |
| 2 | Replace suggested prompts with capability-showcasing, labeled set | S | ★★★ |
| 3 | Widen composer placeholder/hint | XS | ★★ |
| 4 | Key insider/smart-money panels to the last-discussed ticker (not only focused filing) | M | ★★ |
| 5 | De-emphasize manual Ingest; add a "you can just ask" hint near it | S | ★★ |
| 6 | Tooltip on the verification badge | XS | ★ |
| 7 | Chat-dominant layout default (sources collapsible) | M | ★ |
| 8 | Chat persistence (localStorage) | M | ★ |

**Done in this pass:** #1, #2, #3 (the P0 discoverability fixes). The rest are
queued in `docs/TODO.md`.
