# Hosting & AI Options — Decision Aid

> **Status: brainstorm / decision aid for LATER.** Nothing here commits you to anything. You are currently
> solo, and your only real pain is *rate limits*, not dollars. This doc exists so that when you decide to put
> this in front of other people, you can pick fast instead of re-researching from scratch.
>
> **All prices were pulled in June 2026 and WILL drift.** Re-verify before you commit money. Sources are
> cited inline.

> ### ⚡ TL;DR for "what can I do absolutely free *right now*"
> Gemini's free tier was cut 50–80% in late 2025 (~250 req/day on Flash) — that daily cap is what's blocking you
> from building and demoing. **Fix, already wired into the code:** the LLM router now accepts a
> `"<provider>/<model>"` prefix (`cerebras` / `groq` / `mistral` / `ollama`), so you can point synthesis + the
> fast model at a far more generous free tier with **zero code change — just `.env`**:
> - **Cerebras** — ~**1M tokens/day** free, no credit card, very fast. → `SYNTHESIS_MODEL=cerebras/llama-3.3-70b`
> - **Mistral** — ~**1B tokens/month** free. · **Groq** — ~1k req/day, fastest streaming.
> - **Ollama** — fully **local, no key, no limit, no signup** → `SYNTHESIS_MODEL=ollama/qwen2.5`.
>
> Embeddings are already local ($0). So with Cerebras *or* Ollama you can build/iterate **unlimited at $0**.
> Demoing to others still needs hosting (§1) — but it's no longer gated on a daily LLM cap. See §2.

## 0. The shape of this project (why generic advice won't do)

This is not a stateless CRUD app, and it's not a pure serverless toy. The architecture has three traits that
dominate every hosting decision:

1. **LanceDB is embedded and on-disk.** It's a library reading/writing files (Lance/Parquet) on a local path,
   not a network database you connect to. That means the backend needs a **real, persistent filesystem** that
   survives restarts. This is the single fact that kills most "serverless" options for the *backend*.
2. **Embeddings are now 100% local** (fastembed/ONNX `bge-large` on CPU, $0, no API). So your embedding rate-limit
   pain is *already solved* the moment you leave AI Studio — it was never a cost problem, it was a free-tier
   throttle. The CPU cost of embedding just becomes "do I have enough cores," not "do I have API budget."
3. **The only paid AI need is synthesis** (currently Gemini 2.5 Flash) plus a small fast-model role
   (table summaries / verification). Routing is already provider-agnostic by model-name prefix
   (`claude-`/`gemini-`/`gpt-`/`local-`), so switching providers is a config + key change, not a rewrite.
   **This is a huge strategic asset** — it means you can chase the cheapest synthesis provider freely and even
   mix providers (cheap model for table summaries, better model for final synthesis).

Implication that recurs throughout this doc: **split the deployment.** The React/Vite frontend is a static
build — host it where static hosting is free and global. The FastAPI + LanceDB backend wants a box with a disk —
host *that* somewhere with a persistent volume. Do not try to force both onto one platform.

---

## 1. Hosting options

### What the backend actually needs
- Persistent disk for the LanceDB files (your SEC corpus + embeddings). Even a modest multi-company corpus is
  comfortably single-digit GB; budget for growth but you're not in TB territory.
- Enough RAM/CPU to run ONNX embedding on CPU without thrashing. `bge-large` on CPU is the heaviest local op —
  **1 GB RAM is tight; 2–4 GB is the comfortable floor.** This nudges you away from the very cheapest 256–512 MB tiers.
- A long-lived process (FastAPI), not a cold-start-per-request function. RAG synthesis calls can run many
  seconds; serverless function timeouts and cold ONNX model loads are a bad match.

### Comparison (side-project scale, ~June 2026 pricing)

| Platform | Backend fit (FastAPI + on-disk LanceDB) | Static FE | Rough $/mo (backend) | Ease |
|---|---|---|---|---|
| **AWS EC2 t4g.small (free trial)** | Good — real box, real disk | (use elsewhere) | **$0** thru Dec 31 2026, then ~$12+EBS | Medium (you manage the box) |
| **AWS Lightsail** | Good — VPS-like, predictable | (use elsewhere) | $5 (512MB/IPv4) – $12 (2GB) | Easy-ish |
| **AWS Lambda** | **Bad** — no persistent local FS, cold starts, 15-min cap; embedded LanceDB needs a disk (EFS is awkward/slow for this) | n/a | n/a | n/a |
| **Vercel** | **Bad for backend** — serverless functions, ephemeral FS, execution-time caps. **Great for the FE.** | Excellent | n/a (FE free) | Easy |
| **Fly.io** | **Very good** — real VMs + cheap persistent volumes, scale-to-zero possible | OK | ~$2 VM + $0.15/GB vol; realistically ~$8–15 with traffic | Medium |
| **Render** | Good — managed web service + persistent disk add-on | OK (static free) | Disk $0.25/GB/mo; persistent-disk service needs paid tier (~$7+ instance, Pro workspace $25) | Easy |
| **Railway** | Good — usage-based, volumes supported | OK | Usage-based; small app often ~$5–15 | Easy (best DX) |
| **Cloudflare Pages** | n/a for backend | **Excellent** (unlimited bandwidth, commercial OK) | $0 | Easy |
| **Cloudflare Workers** | **Bad** for this backend — no persistent POSIX FS for embedded LanceDB; not a place to run FastAPI+ONNX | n/a | $0–5 | n/a |
| **Hetzner VPS** | **Very good** — cheapest real compute | (use elsewhere) | CPX22 (2 vCPU/4GB) ~$9.49/mo | Medium (DIY) |
| **DigitalOcean** | Good — well-trodden | OK | Basic Droplet (2vCPU/4GB) ~$24/mo | Easy-ish |

Pricing sources: Fly.io VM ~$2/mo + volumes $0.15/GB/mo ([Fly docs](https://fly.io/docs/about/pricing/), [costbench](https://costbench.com/software/developer-tools/flyio/)); Render disk $0.25/GB/mo, Pro workspace $25/mo ([Render pricing](https://render.com/pricing)); Lightsail $3.50 (IPv6-only) / $5 (IPv4) entry ([netcomlearning](https://www.netcomlearning.com/blog/aws-lightsail)); EC2 t4g.small free trial extended to Dec 31 2026 ([AWS re:Post](https://repost.aws/articles/ARi_gf6vo6TuqNtMQdiYPKyA/announcing-amazon-ec2-t4g-free-trial-extension)); Hetzner CPX22 ~$9.49/mo post-April-2026 ([costgoat](https://costgoat.com/pricing/hetzner), [Better Stack](https://betterstack.com/community/guides/web-servers/digitalocean-vs-hetzner/)); DigitalOcean Basic ~$24/mo ([Better Stack](https://betterstack.com/community/guides/web-servers/digitalocean-vs-hetzner/)); Vercel Hobby free / non-commercial ([costbench](https://costbench.com/software/developer-tools/vercel/)); Cloudflare Pages unlimited bandwidth free, Workers $5 base ([DevToolReviews](https://www.devtoolreviews.com/reviews/cloudflare-pages-pricing-bandwidth-limits-2026), [morphllm](https://www.morphllm.com/comparisons/cloudflare-workers-vs-vercel)).

> **Free-tier reality, updated June 2026 (these changed — the rows above are pricing, not free tiers):**
> - **Fly.io no longer has a free tier** for new users — credit card required, trial only (~2 VM-hours / 7 days).
> - **Railway has no permanent free tier** — a one-time $5 trial credit, then the Hobby plan at $5/mo.
> - **Render still has a real free tier** (512 MB web service, $0) — but it **cold-starts after 15 min idle**
>   (30–60 s spin-up) and a *persistent disk* requires a paid instance.
>
> **All-in-one (one platform hosts FE + BE + disk, one bill, one dashboard):** with Fly/Railway free tiers gone
> and a single dashboard being less hassle solo, going all-in-one is now competitive with the "split" below:
> - **Railway** — best DX; one project = static FE + FastAPI BE + volume (+ a one-click Postgres if you adopt
>   pgvector). ~$5/mo, no free tier. **Best "keep the current architecture, one platform" answer.**
> - **Render** — static site + web service + managed Postgres + disk in one place; has a free tier (cold starts).
> - **Single-vendor incl. AI** (Cloudflare Pages+Workers+**Workers AI**, or Vercel + AI Gateway) gets you
>   FE+BE+inference on one bill — **but only if you re-architect to stateless** (pgvector + hosted embeddings);
>   they can't run today's FastAPI+ONNX+LanceDB. **Replit** is genuinely all-in-one (dev+host+AI) but weak for a
>   production FastAPI-with-disk. Sources:
>   [Railway vs Render vs Fly.io (solo, 2026)](https://devtoolpicks.com/blog/railway-vs-render-vs-fly-io-solo-developers-2026),
>   [Fly.io free tier 2026](https://www.saaspricepulse.com/blog/flyio-free-tier-2026),
>   [Render real free tiers 2026](https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026).

### Why Lambda / Workers / Vercel-backend keep failing for *this* app
Embedded LanceDB is the issue, not FastAPI. These platforms give you an ephemeral filesystem that vanishes
between invocations. You'd have to mount network storage (EFS) or push LanceDB to object storage, both of which
fight the "embedded, on-disk, fast local reads" design that made LanceDB attractive in the first place. Long
RAG calls also collide with serverless timeouts and per-invocation cost. **Don't.** They're great for the
static frontend — use them there.

> Caveat — **uncertain:** LanceDB *can* be pointed at object storage (S3/R2) in some configs, which would in
> principle unlock serverless. But for a solo side-project this adds latency and complexity for no real benefit.
> Treat "serverless backend" as a non-goal unless you later re-architect deliberately.

### The vector store is the decision that controls everything

Every "no serverless backend" conclusion above rests on **one** fact: LanceDB is *embedded and on-disk*. Swap it
for a **network/managed** vector store and the backend becomes stateless — and most of the cheap/free hosting
options that were ruled out re-open. So it's worth knowing the alternatives before committing.

| Alternative | Model | Free tier (June 2026) | Why you'd switch |
|---|---|---|---|
| **Stay on LanceDB (embedded)** | On-disk lib | $0, no account | Simplest, fastest local reads, corpus is reproducible. **Forces a box with a disk.** |
| **pgvector** (Postgres ext.) | Server DB | **Free** on Supabase / Neon free tiers | Backend goes stateless; one store for vectors *and* app/user data; you likely already know Postgres |
| **Qdrant Cloud** | Managed | **1 GB cluster, no card** | Purpose-built, strong hybrid search |
| **Chroma Cloud / Zilliz** | Managed | Generous free / 1 collection | Easy managed RAG stores |
| **Turbopuffer** | Object-storage-backed | Usage-based, very cheap | Built *for* serverless — vectors live on S3/R2 |
| **Pinecone** | Serverless | ~$70/mo at real scale | Most mature; priciest |
| **LanceDB Cloud** | Managed Lance | (re-verify rates) | Least migration — same engine, just hosted |

**Does this change the recommendation? It forks it:**
- **Keep embedded LanceDB** → everything below stands; you need a persistent disk.
- **Move to pgvector (Supabase/Neon free)** → the backend can be stateless, and *"avoid Lambda/Workers/Vercel"*
  no longer applies — cheaper/serverless/all-in-one hosting opens up.

**The catch most comparisons miss:** swapping the vector DB *alone* does **not** fully unlock serverless, because
your **local `bge-large` ONNX embeddings** are themselves a serverless-blocker — a cold-starting function loading
a ~1 GB ONNX model per invocation is miserable. To truly go serverless you'd *also* move embeddings to a hosted
embedder (Gemini/OpenAI/Voyage). **Net: the vector-store choice and the embedding choice have to move together.**
At solo scale, embedded LanceDB + local embeddings is still the simplest $0 option; the alternatives buy
statelessness you don't yet need. Pricing sources: [MarkTechPost vector DB 2026](https://www.marktechpost.com/2026/05/10/best-vector-databases-in-2026-pricing-scale-limits-and-architecture-tradeoffs-across-nine-leading-systems/),
[buildmvpfast vector DB pricing (June 2026)](https://www.buildmvpfast.com/api-costs/vector-db).

### Recommended split
- **Frontend (React/Vite static build): Cloudflare Pages.** Free, global CDN, unlimited bandwidth, commercial use
  allowed (unlike Vercel Hobby, which is non-commercial — a real gotcha if this ever earns a dollar). Vercel is a
  fine alternative if you already like its DX and stay non-commercial.
- **Backend (FastAPI + LanceDB):** depends on phase —
  - **Now / POC:** your own laptop, or **AWS EC2 t4g.small** on the free trial (literally $0 through end of 2026).
  - **Small public beta:** **Fly.io** (best balance of real disk + low cost + scale-to-zero) or **Railway** (best
    DX, near-zero ops). Both let you attach a volume and forget about it.
  - **Cost-floor / you like a shell:** **Hetzner CPX22 (~$9.49/mo)** is the cheapest *real* box and won't surprise
    you with usage bills. Trade-off: you own patching, backups, TLS.

**Opinion:** For your profile (solo, hates fiddling, wants predictable bills), the sweet spot is
**Cloudflare Pages (FE) + Fly.io or Railway (backend)**. Pick Hetzner only if you actively *enjoy* running a box
or want the absolute lowest fixed cost.

---

## 2. AI / LLM cost options (synthesis + small fast-model role)

Your routing layer is provider-agnostic, so this is purely a price/quality/latency shopping exercise. You have
**two roles**: (a) **synthesis** — the user-facing answer, quality matters; (b) **fast/cheap** — table
summaries & verification, where you want dirt-cheap and fast.

### Free tiers — what's actually generous (and what's now wired in)

"Free with no rate limits" doesn't exist — the limit *is* how a provider caps its cost. But you don't have to be
stuck on Gemini's: **Google cut the AI Studio free tier 50–80% in late 2025** (~250 req/day, 10 RPM on Flash),
and that daily cap is your build/demo blocker. Other free tiers are dramatically more generous:

| Provider | Free tier (no credit card) | Notes |
|---|---|---|
| **Cerebras** | ~**1M tokens/day** | Most generous by volume; very fast. **Best free default.** |
| **Mistral** (la Plateforme) | ~**1B tokens/month** | Could cover an entire side-project alone |
| **Groq** | ~30 RPM / **1k req/day** (Llama 3.3 70B) | Fastest token streaming |
| **GitHub Models** | 100+ models, generous daily (preview) | Good for experimentation |
| **Gemini Flash** (status quo) | ~250 req/day, 10 RPM | What's biting you now |
| **Ollama (local)** | **unlimited, $0, no signup** | Quality/speed bound by your machine |

**Wired into the code (June 2026):** the router accepts `"<provider>/<model>"` for `cerebras`/`groq`/`mistral`/
`ollama` via an OpenAI-compatible `base_url` swap — switching is a one-line `.env` change, no code. And because
the router is provider-agnostic you can **fan out across providers** (each has independent limits) to multiply
free capacity. Sources:
[TokenMix free LLM APIs 2026](https://tokenmix.ai/blog/free-llm-apis-2026-every-provider-free-tier-tested),
[Flywheel free LLM tiers 2026](https://wetheflywheel.com/en/ai-model-access/free-llm-api-tiers-2026/).

### Rough $/1M tokens (input / output), ~June 2026

| Provider / model | Input | Output | Notes |
|---|---|---|---|
| **Gemini 2.5 Flash** (current) | $0.30 | $2.50 | Your status quo; good quality, 1M context |
| **Gemini 2.5 Flash-Lite** | $0.10 | $0.40 | Cheapest Gemini; ideal for the fast role |
| **Amazon Nova Micro** (Bedrock) | $0.035 | $0.14 | **Cheapest serious option**; great for fast role |
| **Amazon Nova Lite** (Bedrock) | $0.06 | $0.24 | Cheap synthesis candidate |
| **Claude Haiku 4.5** (Bedrock or direct) | $1.00 | $5.00 | Higher quality fast model; pricier |
| **OpenAI GPT-5 nano** | $0.05 | $0.40 | Cheap; comparable to Flash-Lite |
| **OpenAI GPT-5 mini** | $0.25 | $2.00 | Mid; near Gemini Flash on price |
| **Groq (Llama 3.3 70B)** | ~$0.59 | ~$0.79 | Open model, very fast; cheaper small models avail |
| **Together / Fireworks (Llama 3.3 70B)** | ~$0.88 | ~$0.88 | Open-weight host |
| **DeepInfra (Llama 3.1 8B)** | ~$0.06 | ~$0.06 | Cheapest open-weight small models |

Sources: Gemini 2.5 Flash $0.30/$2.50, Flash-Lite $0.10/$0.40 ([devtk](https://devtk.ai/en/models/gemini-2-5-flash/), [pricepertoken](https://pricepertoken.com/pricing-page/model/google-gemini-2.5-flash-lite)); Nova Micro $0.035/$0.14, Nova Lite $0.06/$0.24 ([bacancy](https://www.bacancytechnology.com/blog/aws-bedrock-pricing), [go-cloud](https://go-cloud.io/amazon-bedrock-pricing/)); Claude Haiku 4.5 $1/$5 ([cloudzero](https://www.cloudzero.com/blog/claude-api-pricing/), [pricepertoken](https://pricepertoken.com/pricing-page/model/anthropic-claude-haiku-4.5)); GPT-5 nano $0.05/$0.40, GPT-5 mini $0.25/$2.00 ([pricepertoken nano](https://pricepertoken.com/pricing-page/model/openai-gpt-5-nano), [pricepertoken mini](https://pricepertoken.com/pricing-page/model/openai-gpt-5-mini)); Groq/Together/Fireworks/DeepInfra ranges ([cloudzero Groq](https://www.cloudzero.com/blog/groq-pricing/), [aipricing.guru Together](https://www.aipricing.guru/together-pricing/), [costbench DeepInfra](https://costbench.com/software/llm-api-providers/deepinfra/)).

### How much will you actually spend? (back-of-envelope)
RAG synthesis is **input-heavy** (you stuff retrieved filing chunks into the prompt) and **output-light** (a
paragraph or two). Say a typical answer is ~8K input tokens + ~800 output tokens.

- On **Gemini 2.5 Flash**: (8K×$0.30 + 0.8K×$2.50)/1M ≈ **$0.0044/query** → ~$0.44 per 100 queries.
- On **Nova Lite**: (8K×$0.06 + 0.8K×$0.24)/1M ≈ **$0.00067/query** → ~$0.07 per 100 queries.
- On **Gemini Flash-Lite**: ≈ **$0.0011/query** → ~$0.11 per 100 queries.

**Translation: at solo/side-project volume your synthesis bill is pennies regardless of provider.** A few
hundred queries a month is well under $1 on any of the cheap options. The reason to move off the AI Studio free
tier is **rate limits, not cost** — a paid Gemini key removes the per-minute and per-day caps that are biting
you now.

### Recommendations
- **$0, unblock today (recommended for the POC):** switch synthesis + fast model to **`cerebras/llama-3.3-70b`**
  (~1M tok/day free, no card, fast) — or **`ollama/qwen2.5`** for fully-local/offline with no key or limit.
  One-line `.env` change; the routing is already in the code. Removes the daily-cap pain at $0.
- **Cheapest *paid* path, lowest friction:** Get a **paid Gemini API key** and stay on **Gemini 2.5 Flash** for
  synthesis, **Flash-Lite** for the fast role. Zero code change, costs ~cents/month at your volume. Worth it once
  you want the polish/quality of Flash without juggling free-tier providers.
- **Cheapest absolute $/token:** **Amazon Nova Lite** (synthesis) + **Nova Micro** (fast role) via Bedrock —
  roughly 5–7× cheaper than Flash. But it adds AWS/Bedrock setup overhead and the savings are pennies at your
  scale, so only worth it if you're already on AWS or expect real volume.
- **Quality lever (kept cheap):** route the *final* synthesis to **Claude Haiku 4.5** when you want crisper
  answers, while keeping table-summary/verification on Nova Micro or Flash-Lite. Your prefix router makes this
  a config change.
- **Groq** is worth a look purely for **latency** (very fast token streaming) if response speed becomes a UX
  priority — not for cost at this scale.

### Self-hosting open models on a GPU — *don't, yet*
A GPU box (cloud or owned) is **not cheaper at low volume.** A modest cloud GPU runs hundreds of dollars/month
24/7; you'd need to be doing *enormous* synthesis volume before amortizing that beats $0.001/query API calls.
Self-hosting only makes sense for privacy/compliance requirements or very high sustained throughput — neither
applies to a solo SEC-filings side-project. **Use hosted APIs.**

---

## 3. Embeddings

**You already made the right call: local embeddings (`bge-large` ONNX/fastembed on CPU) = $0, no API, no rate
limit.** Keep this as the default. It removes your single biggest source of free-tier throttling (the
per-minute embedding cap) and makes corpus ingestion a pure compute problem you control.

When a **hosted embedder** or **LanceDB Cloud** would start to matter:
- **CPU embedding throughput becomes a bottleneck** — if you're re-embedding large EDGAR corpora and CPU
  ingestion is painfully slow, a hosted embedding API (e.g. Gemini/OpenAI/Voyage embeddings) or a GPU batch job
  buys speed. At solo scale, just let it run; it's a one-time-per-corpus cost.
- **You go multi-machine / serverless** and no longer have one box owning the LanceDB files — then
  **LanceDB Cloud** (managed, object-storage-backed) starts earning its keep by removing the "who owns the disk"
  problem. Until then it's solving a problem you don't have. *(Pricing not verified here — check current
  LanceDB Cloud rates before considering.)*
- **Embedding quality** — if retrieval relevance is weak, a stronger hosted embedding model can help more than
  any synthesis change. That's a *quality* decision, not a cost one.

**Verdict: local stays the default through every phase below.** Revisit only if ingestion speed or multi-host
deployment forces it.

---

## 4. Other non-code considerations

### Auth & secrets
- **Secrets (API keys):** never in the repo. Use the platform's secret store — Fly secrets / Railway variables /
  Render env groups / or a `.env` on a VPS with `chmod 600`. Your only real secret today is one LLM API key.
- **User auth:** you don't need it for a solo POC. The moment it's public, decide: (a) keep it fully open
  (fine for a read-only research tool, but then put it behind a rate limiter), or (b) add lightweight auth.
  For a small beta, a **single shared password / basic-auth on the backend**, or a hosted auth provider's free
  tier (Clerk/Auth0/Supabase Auth free tiers) avoids you rolling your own. Don't build a user system before you
  have users.

### Monitoring / observability
- **Cheap floor:** platform-native logs (Fly/Railway/Render all stream logs) + an **uptime ping**
  (UptimeRobot/BetterStack free tier hitting a `/health` endpoint).
- **LLM-specific:** log every synthesis call's token counts + provider + latency to a file or simple table.
  This is your early-warning system for both cost and rate-limit issues, and it's a few lines of code.
- Don't pay for an APM/observability SaaS at this stage.

### Cost guardrails (the thing that bites side-projects)
- **Set a hard billing cap / budget alert** on whichever LLM provider you use (Google Cloud budget alert,
  AWS Budgets, OpenAI usage limit). A public RAG endpoint + a scraper = a surprise bill. Do this *before* going
  public, not after.
- **Rate-limit your own backend** (per-IP) so one user (or bot) can't run up your LLM bill or peg your CPU
  embedder.
- Prefer **fixed-price hosting** (Hetzner/Lightsail) over usage-metered (Railway/Fly egress) if predictable
  bills matter more to you than scale-to-zero.

### Backups & persistence for the LanceDB volume
- **This is your real data risk.** The LanceDB files are your only stateful asset. A volume can be lost
  (provider incident, accidental `fly volumes destroy`, droplet rebuild).
- **Backup strategy:** periodic `tar` of the LanceDB directory → push to cheap object storage
  (**Cloudflare R2** has no egress fees, S3/B2 are fine too). A nightly cron is plenty at this scale.
- **Good news:** the corpus is *reproducible* — it's derived from free public EDGAR data + a local embedder. So
  worst case you re-ingest. Backups just save you the re-ingestion time. Keep the ingestion pipeline runnable.
- Note Fly bills volumes even when the machine is stopped, so don't leave orphaned volumes around.

### Compliance / ToS for SEC data
- **SEC EDGAR data is public domain** — you can query, store, and redistribute it. No licensing fee, no
  attribution legally required, but a clear "Data source: SEC EDGAR" note is good etiquette and builds trust.
- **The real obligation is access etiquette:** SEC asks automated clients to (1) send a descriptive
  **`User-Agent`** with contact info, and (2) stay **under their fair-access rate limit (historically ~10
  requests/sec)**. Build polite throttling + caching into your ingestion so you never hammer EDGAR. *(Re-verify
  SEC's current fair-access policy and rate guidance before scaling ingestion.)*
- **Liability framing:** if public, add a plain disclaimer that this is an informational research tool, not
  investment advice, and that LLM synthesis can be wrong — point users to the underlying filing. This is cheap
  insurance for a tool that talks about securities.

---

## 5. Recommended phased path

### Phase 0 — POC now (truly free)
**Goal:** kill the rate-limit pain, keep building, $0.
- **Hosting:** your laptop (or EC2 t4g.small free trial, $0 through Dec 31 2026).
- **AI:** point the models at a generous free tier — **`cerebras/llama-3.3-70b`** (~1M tok/day, no card) or
  fully-local **`ollama/qwen2.5`** (no key, no limit). One-line `.env` change; routing already shipped.
  (A paid Gemini key is the alternative if you'd rather stay on Flash — pennies/mo.)
- **Embeddings:** local `bge-large`, $0.
- **Cost: $0** (Cerebras/Ollama free + local embeddings). If you use a paid LLM key instead, set a budget alert.

### Phase 1 — Small public beta (cheap)
**Goal:** real URL, a handful of users, predictable bill, don't get surprise-billed.
- **Frontend:** **Cloudflare Pages** (free, commercial-OK, unlimited bandwidth).
- **Backend:** **Fly.io** or **Railway** — real VM + persistent volume for LanceDB, scale-to-zero to save money.
  (Hetzner CPX22 ~$9.49/mo if you prefer a fixed-price box you control.)
- **AI:** keep Gemini Flash/Flash-Lite, **or** move the fast role to **Nova Micro** if you want to shave token cost.
- **Must-dos:** per-IP rate limiting, LLM billing cap, nightly LanceDB backup to R2, `/health` + UptimeRobot,
  "not investment advice" disclaimer, EDGAR `User-Agent` + throttle.
- **Cost: ~$5–15/mo** (backend) + **pennies** (LLM). FE and embeddings free.

### Phase 2 — If it grows (real users / volume)
**Goal:** handle load and watch costs as LLM usage scales linearly with traffic.
- **Hosting:** scale up the same backend box (more RAM/CPU for concurrent CPU embedding + synthesis), or split
  ingestion (batch, background) from serving. Consider a managed Postgres only if you outgrow embedded LanceDB's
  single-box model — at which point **LanceDB Cloud** becomes worth pricing out.
- **AI:** this is where per-token price starts to matter. Route synthesis to the best $/quality option
  (**Nova Lite** cheapest, **Gemini Flash** balanced, **Claude Haiku 4.5** for quality), fast role on
  **Nova Micro**. Add prompt caching (Bedrock/Anthropic/OpenAI all offer it) to cut the input-heavy RAG cost.
- **Embeddings:** consider a GPU batch job or hosted embedder *only if* CPU ingestion is the bottleneck.
- **Observability:** add lightweight LLM call logging dashboards; revisit a real uptime/APM tool if users depend
  on it.
- **Cost:** backend scales with the box (tens of $/mo); LLM scales with queries but is still cheap per-query —
  your guardrails and caching keep it sane.

---

## TL;DR

- **Your problem today is rate limits, not money — and it's fixable at $0.** Gemini's free tier was gutted
  (~250 req/day). The router now takes `"<provider>/<model>"`, so switch to **`cerebras/llama-3.3-70b`**
  (~1M tok/day free, no card) or fully-local **`ollama/qwen2.5`** (no key, no limit) with a one-line `.env`
  change. A paid Gemini key (pennies/mo) is the alternative if you prefer Flash's quality.
- **Vector store is the pivot:** *embedded LanceDB* is the single fact that forces a disk and rules out
  serverless. Moving to **pgvector (Supabase/Neon free)** makes the backend stateless and re-opens cheaper
  hosting — but you'd *also* have to move embeddings off local CPU, so don't bother until you need it.
- **Deploy:** keep embedded LanceDB → either **split** (static FE on **Cloudflare Pages**, free + commercial-OK;
  FastAPI+disk backend on a real box) **or go all-in-one** on **Railway** (~$5/mo) / **Render** (free tier, cold
  starts) — one platform for FE+BE+disk. Heads-up: **Fly.io and Railway no longer have free tiers** (2026).
  **Avoid Lambda/Workers/Vercel for the backend** unless you re-architect to a stateless store.
- **Embeddings: keep them local ($0).** That decision already solved your worst throttle. Only revisit for
  ingestion speed or multi-host setups.
- **Cheapest-token path** (if you ever want it): **Amazon Nova Lite/Micro** on Bedrock, ~5–7× cheaper than
  Flash — but the savings are pennies at your scale, so don't bother until volume justifies the AWS overhead.
- **Don't self-host a GPU** at low volume — hosted APIs win on cost until you're doing huge throughput.
- **Before going public:** set an LLM billing cap, rate-limit your endpoint, back up the LanceDB volume to R2,
  add a "not investment advice" disclaimer, and set a polite EDGAR `User-Agent` + throttle.
- **Phase costs:** POC ~$0–2/mo · Beta ~$5–15/mo · Growth = tens of $/mo + cheap-per-query LLM.

---

> ⚠️ **Prices and free-tier terms change frequently.** Every number above was pulled June 2026 and is cited.
> Re-verify current pricing and ToS (especially LLM token rates, free-tier limits, and SEC fair-access rules)
> before committing money or going public.
