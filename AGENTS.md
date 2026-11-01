# AGENT PROMPT: ControlFinder, an evaluated RAG + LangGraph system over NIST SP 800-53

> Paste this whole file as the first message to your coding agent (Claude Code), or save it in the repo root as `CLAUDE.md`.
> Everything below is addressed to the agent.

---

## 0. Who you're working with and how

You are building this project **with** me, Jude, a software engineer with ~2 years of experience (TypeScript/Node, Python/FastAPI, Java, React, AWS). I have shipped LLM agents and eval harnesses in production, but **I have never built RAG, embeddings, vector search, or LangGraph**. That's the gap this project closes.

There are two goals, and they have **equal weight**:

1. **Build it correctly**: a working, evaluated, reproducible system, in a single day.
2. **Make me interview-ready**: by the end, I must be able to defend every decision, number and limitation to a skeptical senior engineer, with no notes. A system I can't explain is worth zero to me.

### Teach-mode protocol (mandatory, never skip)

At the end of **every phase**:

1. Write `docs/learn/NN-<phase-name>.md` containing:
   - **What we built**: in plain language, plus file paths.
   - **How it works**: the mechanism, step by step. Include the key SQL or code snippets, with comments.
   - **Decisions**: for each choice, explain what we chose, what the alternatives were, and why we chose this one. Where a number backs the decision, cite the number from `results/`.
   - **Gotchas we hit**: anything that broke or surprised us, and how we fixed it.
   - **Interview questions**: 5–8 questions a sharp interviewer would ask about this phase, each with a model answer of 3–6 sentences that uses *our* actual numbers.
2. Append each decision to `DECISIONS.md` in this format: date | decision | alternatives | evidence.
3. **STOP and quiz me.** Ask me 3 questions from that phase, one at a time. Wait for my answer each time. Grade it honestly: say what was right, what was missing, and what an interviewer would push on. **Do not continue to the next phase until I type `next`.**
4. Make a git commit for the phase with a clear message.

If I ask "why?" at any point, answer at depth before continuing. Never hand-wave.

### Hard rules

- **Never invent numbers.** Every metric in any doc, README or answer must come from a script run and be saved in `results/*.json`. Tables in docs are generated from those files, never typed by hand.
- **The test split is sealed.** Tune only on `dev`. Run on `test` exactly once, in Phase 6. If something forces a re-run, write it down in `DECISIONS.md` and explain why.
- **Write the retrieval layer by hand.** Use raw SQL with psycopg for vector search, full-text search, fusion and reranking. **No LangChain or LlamaIndex retrievers, vector stores, or chains for retrieval.** LangGraph is only for the agent layer (Phase 5).
- **Reproducible.** Fix the seeds, pin dependency versions in `pyproject.toml` (choose stable releases that are at least 2 weeks old), and use a single command per step (`make ingest`, `make eval`, and so on).
- **Small, readable code.** Prefer obvious over clever. Every module gets a docstring explaining *why* it exists.
- **Report negative results honestly.** If hybrid search doesn't beat keyword search, or the agent doesn't beat the plain pipeline, say so. That counts as a finding, not a failure.
- If a data source URL or format differs from what this prompt says, **stop and tell me**. Don't guess.

---

## 1. Project overview

**ControlFinder**: given a question about security or compliance, it retrieves the relevant **NIST SP 800-53 Rev 5** controls and answers with cited control IDs, or **declines to answer** when the corpus doesn't support one.

**Why this design is interesting (put this in the README intro):** most RAG demos are never measured. This one has a **free, authoritative answer key**. NIST publishes official mappings from **CSF 2.0 subcategories → SP 800-53 controls** (the CSF 2.0 Informative References). Each CSF subcategory becomes a query, and its mapped controls become the ground truth. That means we can measure retrieval objectively, with recall@k, MRR and nDCG, instead of just eyeballing outputs.

### Architecture (target)

```
                    ┌───────────────────────────── LangGraph agent (Phase 5) ─────────────────────────────┐
question ──► [scope check] ──► [retrieve] ──► [grade evidence] ──► good? ──► [generate w/ citations] ──► [verify citations] ──► answer
                 │                                  │ weak                                                       │ invalid
                 ▼                                  ▼                                                            ▼
             [abstain]                    [rewrite query] ──(max 2 loops)──► [retrieve]                     [abstain]

retrieve = hand-written:  Postgres FTS  +  pgvector ANN  ──► RRF fusion ──► cross-encoder rerank ──► top-k
```

### Stack

| Piece | Choice |
|---|---|
| Language / API | Python 3.11+, FastAPI, `uv` for environment and dependencies |
| Database | Postgres 16 + pgvector (Docker Compose), psycopg 3 |
| Keyword search | Postgres full-text search (`tsvector`, `ts_rank_cd`) **and** true BM25 (`rank_bm25`) for comparison |
| Embeddings | Primary: `BAAI/bge-small-en-v1.5` (local, sentence-transformers). Stretch: OpenAI `text-embedding-3-small` |
| Reranker | `BAAI/bge-reranker-base` cross-encoder (local, CPU is fine) |
| LLM | Anthropic Claude via API (read the key from `.env`). Wrap it so swapping providers is a single-line change |
| Agent | LangGraph (`StateGraph`) |
| Tests / CI | pytest, GitHub Actions with a Postgres service container |

### Repo layout

```
controlfinder/
  docker-compose.yml        # postgres + pgvector
  Makefile                  # make up / ingest / embed / eval / agent-eval / test / report
  pyproject.toml
  .env.example              # ANTHROPIC_API_KEY=, OPENAI_API_KEY= (optional), DATABASE_URL=
  data/raw/                 # downloaded source files (gitignored if large)
  data/processed/           # normalized JSONL
  src/controlfinder/
    ingest/                 # parse OSCAL, normalize IDs, build chunks
    index/                  # embeddings, SQL schema, indexes
    retrieval/              # fts.py, bm25.py, dense.py, fusion.py, rerank.py, pipeline.py
    eval/                   # datasets.py, metrics.py, bootstrap.py, run_retrieval_eval.py
    generation/             # prompt, generate, citation check, judge
    agent/                  # langgraph graph, nodes, state
    api/                    # FastAPI app
    obs/                    # query logging
  results/                  # every metric as JSON (committed)
  docs/learn/               # teach-mode notes per phase
  DECISIONS.md
  README.md
  tests/
```

---

## 2. One-day schedule

Total is about 13 hours. **If we fall behind, cut the stretch items. Never cut the teach-mode checkpoints.**

| Phase | Time | Must-have | Stretch |
|---|---|---|---|
| 0. Setup | 0:45 | repo, Docker, schema, Makefile | – |
| 1. Data + chunking | 1:30 | OSCAL parse, ID normalization, 3 chunking strategies | – |
| 2. Eval set + metrics + baselines | 2:00 | gold set, dev/test split, metrics, FTS / BM25 / dense baselines | – |
| 3. Hybrid + rerank + ablations | 2:30 | RRF, reranker, chunking ablation, bootstrap CIs | OpenAI embeddings, HyDE |
| 4. Generation + judging | 1:30 | cited answers, citation precision, blind LLM judge | – |
| 5. LangGraph agent + abstention | 2:00 | graph, loop bound, threshold sweep, agent vs plain pipeline | – |
| 6. Final test run, CI, observability, README | 1:30 | sealed test run, CI regression gate, query log, README | tiny UI |
| 7. Interview drill | 1:00 | mock interview | – |

---

## 3. Phases in detail

### Phase 0: Setup

1. `docker-compose.yml` with `pgvector/pgvector:pg16`, a named volume and a health check.
2. Schema (`src/controlfinder/index/schema.sql`):
   - `controls(id text pk, family text, title text, statement text, guidance text, parent_id text null, is_enhancement bool)`
   - `chunks(chunk_id text pk, strategy text, control_id text, parent_control_id text, text text, tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED, embedding vector(384))`
     - Use dimension 384 for bge-small. Use a separate column or table if we add OpenAI's 1536.
   - A GIN index on `tsv`. An **HNSW** index on `embedding` with `vector_cosine_ops`.
   - `query_log(id, ts, query, pipeline, retrieved jsonb, scores jsonb, latency_ms jsonb, decision text)`
3. Makefile targets, `.env.example`, and a pytest smoke test that connects to the DB.

**Teach me:** why pgvector instead of a dedicated vector DB, at this scale and in general. HNSW vs IVFFlat: how each works, their build and recall tradeoffs, and what `ef_search` / `lists` / `probes` do. Why cosine similarity, and what normalized embeddings mean. Why a generated `tsvector` column.

### Phase 1: Data and chunking

1. **Corpus:** NIST SP 800-53 Rev 5 catalog in **OSCAL JSON** from NIST's official `oscal-content` GitHub repository (usnistgov). Find the current file path, show it to me, and download it. Parse each control and enhancement: ID, title, statement parts, and guidance (the "discussion" part). Handle parameter placeholders in the statement text (render `{{ insert: param, ... }}` as a readable label). Skip withdrawn controls, and log how many were skipped.
2. **ID normalization (the most important gotcha):** OSCAL uses IDs like `ac-2` and `ac-2.1`. NIST mapping spreadsheets typically use forms like `AC-2`, `AC-02` or `AC-2(1)`. Write `normalize_control_id()` that handles all of these, plus **exhaustive unit tests**. Every enhancement must know its `parent_control_id`.
3. **Three chunking strategies**, all stored in `chunks` with a `strategy` label:
   - `A_control_only`: base control statement + guidance. Enhancements are excluded.
   - `B_control_plus_enh`: base control + all its enhancements merged into one chunk. Watch the length, and note the embedding model's max tokens (bge-small truncates at 512 tokens). Log how many chunks get truncated.
   - `C_separate`: every control and enhancement is its own chunk, carrying `parent_control_id`.
4. Print corpus stats: number of controls, enhancements, withdrawn controls, and a token-length distribution per strategy. Save to `results/corpus_stats.json`.

**Teach me:** what chunking is and why it matters for recall. What happens when a chunk exceeds the model's token limit (silent truncation). Why strategy C requires **parent-level deduplication** at evaluation time. Why ID normalization bugs silently wreck your metrics.

### Phase 2: Eval set, metrics and baselines

1. **Gold set:** download the **CSF 2.0 Informative References** spreadsheet from NIST (nist.gov → cyberframework → informative references; there's a direct xlsx download of all references in the Core). Filter to **SP 800-53 Rev 5** references. Build `subcategory_id → {normalized base control IDs}`. Map enhancement references to their parent control, and write that decision down.
   - Report how many subcategories have at least one 800-53 mapping, and the number of controls per query (min, median, max). Expect roughly a hundred-odd mapped subcategories. **That's small**, which is why the next step exists.
2. **Query augmentation (to get a usable sample size):** NIST also publishes **CSF 2.0 Implementation Examples** (xlsx). Each subcategory has several example statements. Build queries of two types:
   - `subcat`: the subcategory's own text.
   - `example`: each implementation example, inheriting its subcategory's gold set.
   If the examples file isn't usable, tell me and continue with subcategories only.
3. **Split by subcategory, not by query** (seeded, 70% dev / 30% test). All examples of a subcategory land in the same split. **Explain leakage to me:** splitting by query would put near-duplicate examples of the same subcategory on both sides, which inflates test scores.
4. **Metrics** in `eval/metrics.py`, each with unit tests on hand-computed toy cases: recall@{5,10,20}, precision@{5,10}, MRR, nDCG@10. Compute metrics **at the parent-control level**: deduplicate retrieved chunks to their parent, keeping first-occurrence rank.
5. **Bootstrap confidence intervals** (`eval/bootstrap.py`): resample queries 1,000 times and report 95% CIs. When comparing two systems, use a **paired bootstrap** on per-query differences.
6. **Baselines** on dev, using strategy `C_separate`:
   - `fts`: Postgres `ts_rank_cd` (via `websearch_to_tsquery` or `plainto_tsquery`; explain the choice)
   - `bm25`: `rank_bm25` over the same chunk texts
   - `dense`: bge-small + pgvector cosine search. **Use the BGE query instruction prefix for queries** as the model card recommends, and explain why queries and passages are embedded differently.
   Save everything to `results/baselines_dev.json`, and print a markdown table with CIs.

**Teach me:** each metric's formula and intuition, and when to use which (recall@k for "did it appear at all," MRR for "how high is the first hit," nDCG for graded ranking). Why Postgres FTS is **not** BM25 (no IDF saturation or length normalization in the same way). Why dense search beats keyword search on paraphrased queries and loses on exact terms or acronyms. **The gold-set limitation:** NIST mappings aren't exhaustive, so some "false positives" are actually correct, which means measured precision is a *lower bound*. Why the CIs matter with roughly 100 subcategories.

### Phase 3: Hybrid search, reranking and ablations (on dev only)

1. **RRF fusion** (`retrieval/fusion.py`): `score = Σ 1/(k + rank_i)` with k=60. Fuse the top 50 from BM25 (or FTS, whichever scored better in Phase 2) with the top 50 from dense. Explain why RRF uses ranks instead of raw scores (scores from different retrievers aren't on comparable scales).
2. **Cross-encoder reranker:** take the top 50 from fusion, score each (query, chunk) pair with bge-reranker-base, and keep the top k. Measure the **latency added per query** (p50 and p95) and report it next to the quality gain.
3. **Ablations.** Change one variable at a time; each row is saved to `results/ablations_dev.json`:

| # | Retrieval | Chunking | Rerank |
|---|---|---|---|
| 1 | bm25 or fts | C | no |
| 2 | dense | C | no |
| 3 | hybrid RRF | C | no |
| 4 | hybrid RRF | C | yes |
| 5 | best of above | A | match row 4 |
| 6 | best of above | B | match row 4 |

   Stretch rows: OpenAI embeddings in place of bge-small, and HyDE (generate a hypothetical passage, embed it instead of the query).
4. Run paired bootstrap tests for: hybrid vs best single retriever, rerank vs no rerank, and the best chunking strategy vs the runner-up. Report which differences are **actually distinguishable from noise**.
5. Pick the **production pipeline config**, and record it in `DECISIONS.md` with the evidence.

**Teach me:** how a bi-encoder (embeddings) differs from a cross-encoder (reranker), and why we use both: recall from the cheap model, precision from the expensive one. The latency-vs-quality tradeoff in numbers. What it means when a difference falls inside the confidence interval.

### Phase 4: Generation and judging

1. **Hand-written question set** (`data/eval/qa.jsonl`), drafted with me:
   - About 40 **answerable** questions, phrased the way a practitioner would ask ("How should we handle offboarding access?"), each with gold control IDs. You draft them, then I review and correct the gold labels. **The labels are mine.**
   - About 30 **unanswerable** questions: out of scope (PCI DSS specifics, a company's own internal policy, legal advice, general trivia) or unsupported by 800-53. The expected behavior is to abstain.
   - Split them 50/50 into dev and test, the same sealed-test rule as before.
2. **Generation prompt:** answer only from the retrieved controls, cite every claim with control IDs in brackets, and say the evidence is insufficient if it is.
3. **Citation check (in code, not by an LLM):** every cited ID must appear in the retrieved set. Report **citation precision** (valid citations ÷ all citations) and **gold-citation recall** (gold controls cited ÷ gold controls).
4. **Faithfulness judge:** an LLM judge scores each answer against its retrieved context from 1 to 5, using a fixed rubric. Use my debiasing method from work: for pairwise comparisons, judge **in both orders** and solo, and only count a win if it's consistent across orders. Store raw judge outputs.
5. Save to `results/generation_dev.json`.

**Teach me:** why citation checks belong in code rather than in the LLM. The known failure modes of LLM judges (position bias, verbosity bias, self-preference) and how each mitigation works. Faithfulness vs correctness: an answer can be faithful to wrong context.

### Phase 5: LangGraph agent and abstention

1. **State** (TypedDict): `question, queries_tried: list[str], retrieved: list[Chunk], top_score: float, attempts: int, decision: str, answer: str | None, citations: list[str], trace: list[dict]`.
2. **Nodes:**
   - `scope_check`: a cheap LLM call that classifies whether the question is about security or privacy controls. If not, go to `abstain`.
   - `retrieve`: calls our hand-written pipeline (Phase 3 config). **No LangChain retrievers.**
   - `grade_evidence`: compare the top reranker score against a **threshold τ**. If it's below τ and `attempts < 2`, go to `rewrite`. If below τ with attempts used up, go to `abstain`. Otherwise go to `generate`.
   - `rewrite`: an LLM rewrites the query (expand acronyms, use control-catalog vocabulary). Increment `attempts`.
   - `generate`: produce the answer with citations (Phase 4 prompt).
   - `verify_citations`: the code check. If any citation is invalid, regenerate once; if it still fails, go to `abstain`.
   - `abstain`: return a structured "insufficient evidence" response that includes the closest controls found.
3. **Loop termination:** cap rewrites at 2 and enforce it in the edge logic, not in the prompt. Add a test proving the graph terminates even when retrieval always scores below τ.
4. **Threshold sweep** on the dev QA set: sweep τ, and for each value compute **answer rate**, **abstention precision/recall** (on unanswerable questions), and **answer accuracy** (on answered questions). Plot the curve to `results/threshold_sweep.png`. Pick τ on purpose, and write down the tradeoff we chose and why.
5. **Agent vs plain pipeline:** on the same dev set, compare (a) a plain pipeline that always retrieves then generates, with no abstention, against (b) the LangGraph agent. Report abstention F1, citation precision, judge score, **p50/p95 latency, and LLM calls per question**. The agent has to *earn* its added complexity. If it doesn't, say so.
6. Log every node transition into `trace`, and write it to `query_log`.

**Teach me:** what LangGraph adds over a plain function chain (explicit state, conditional edges, cycles, and an inspectable trace). Why loop bounds belong in the graph structure. Why abstention is a precision/recall tradeoff and not a single number. How this design maps to "guardrails" and "constraint spaces" in AI job descriptions.

### Phase 6: Sealed test run, CI, observability and README

1. **Run every final config on `test` exactly once.** Save to `results/final_test.json`. Report retrieval metrics with CIs, generation metrics, and agent metrics. If test results differ noticeably from dev, discuss why.
2. **CI regression gate** (`.github/workflows/eval.yml`): spin up a Postgres+pgvector service, load a small fixed fixture (about 30 dev queries with **precomputed embeddings** committed as a fixture, so CI doesn't download models), run retrieval eval, and **fail if recall@10 drops more than 3 points** below `results/ci_baseline.json`. Also run all unit tests.
3. **Observability:** FastAPI endpoints `/search` and `/ask`. Every request writes to `query_log` with the latency of each stage. Add `make report`, which prints p50/p95 latency per stage and the abstention rate from the log.
4. **README.md:**
   - What it is, in 2 lines.
   - The answer-key idea (CSF → 800-53 mappings).
   - An architecture diagram (Mermaid).
   - **Results:** the main ablation table with CIs, the threshold chart, and agent vs pipeline. All generated from `results/`.
   - **Decisions and why:** link to `DECISIONS.md`.
   - **Limitations, stated plainly:** gold mappings aren't exhaustive (so precision is a lower bound); the eval set is small (hence the CIs); the corpus is a single catalog of ~1k items, so this isn't web-scale ANN tuning; QA labels were made by one person.
   - **How I built this with Claude Code:** a short, honest section on how work was split between me and the agent, how outputs were verified (tests, metric unit tests, the sealed test split), and what the agent got wrong that I caught. **Leave this section as a TODO for me to write myself.**
   - How to run: three commands.
5. Stretch: a minimal UI. Skip it if we're behind.

### Phase 7: Interview drill

Act as a skeptical senior interviewer from an AI/RAG team. Run a 45-minute mock interview on this project, using only my answers and our `results/`. Cover: architecture walkthrough, chunking choice, why hybrid, why rerank and what it costs, how I know the numbers are real (sealed test set, CIs, leakage), gold-set limitations, the abstention threshold choice, why LangGraph and whether it was worth it, what I'd do at 100x scale (sharding, ANN parameters, embedding refresh, caching), and what I'd change next. After each answer, grade it and give a stronger version **in my own voice**. Finish with my 5 weakest spots and the exact sentence to say for each one.

---

## 4. Definition of done

- [ ] `make up && make ingest && make eval && make agent-eval` works from a clean clone
- [ ] All unit tests pass, including ID normalization, metrics, and graph termination
- [ ] `results/` contains baselines, ablations, generation, threshold sweep and final test results, all with CIs where applicable
- [ ] The CI workflow is green, and the regression gate is proven to fail when recall is deliberately broken (show me)
- [ ] The README results tables are generated from `results/`
- [ ] `docs/learn/` has a file for every phase, and I passed every quiz
- [ ] `DECISIONS.md` is complete

## 5. What I'll do with it afterwards (for your context only)

I'll put this on my **personal** GitHub and add one resume bullet, written only from `results/final_test.json`, along these lines:

> Built a RAG system over NIST SP 800-53 (~1k controls) on Postgres/pgvector with hand-written hybrid search (BM25 + dense, RRF) and cross-encoder reranking, plus a LangGraph agent that rewrites weak queries and abstains below a tuned threshold; on [N] held-out official CSF→800-53 mappings, raised recall@10 from [X] to [Y] (95% CI)

Start with Phase 0. Before writing any code, summarize the plan back to me in 10 lines or fewer and list anything you think is wrong or risky about it.

---

## Amendments agreed on 2026-10-23

These override the text above wherever they conflict. Each one has a row with its evidence in `DECISIONS.md`.

**Repo and environment**
- The repo root is `RAG/controlfinder/`, not the `RAG/` workspace folder.
- Jude sets a repo-local git identity and uses a personal GitHub account and his own API keys. Never touch global git config. Commits follow Jude's commit style: short lowercase one-line messages, no co-author trailer, explicit paths only.
- No Jira ticket for this project.

**Data**
- The gold set and the implementation examples come from one file: the CSF 2.0 "Informative References in the Core" xlsx (`https://csrc.nist.gov/extensions/nudp/services/json/csf/download?olirids=all`, linked as "Download English (xlsx)" on nist.gov). Column C holds the subcategory, column D the implementation examples (`Ex1: … Ex2: …` in one cell), column E the references.
- That file carries both `SP 800-53 Rev 5.1.1:` and `SP 800-53 Rev 5.2.0:` references. Use only Rev 5.2.0, which matches the OSCAL catalog version.
- Skip withdrawn CSF subcategory rows (`[Withdrawn: …]`). Drop family-level references (`SP 800-53 Rev 5.2.0: CP`, `IR`, `PT`) and log them. Remap references to withdrawn controls through OSCAL's `incorporated-into` link (RA-4 → RA-3) and log them.
- Pin the OSCAL catalog to usnistgov/oscal-content commit `f0de6d8d8c059d374f15e0ae07508d82e370fc1d` and verify a sha256 checksum. Commit the xlsx to `data/raw/`, because its endpoint isn't versioned.

**Retrieval**
- FTS: report both the AND query (`plainto_tsquery`, as written above) and an OR query over the same lexemes, both ranked by `ts_rank_cd`.
- Dense: one partial HNSW index per strategy, `hnsw.ef_search` at least as large as the LIMIT, and the strategy passed as a SQL literal, never a bind parameter (a generic plan can't use a partial index). Compare against `hnsw.iterative_scan` (supported in our pgvector 0.8.7). Always measure HNSW recall against exact search, and record which path ran: at this table size the planner picks an exact sequential scan unless forced (`results/ann_filter_demo.json`).
- Strategy C: retrieve deeper before parent-level dedup, so every system fills k unique parent controls.
- Vector search and FTS are raw SQL. BM25 (`rank_bm25`), RRF fusion and cross-encoder reranking are plain hand-written Python. No retrieval frameworks.

**Eval**
- Bootstrap by subcategory (cluster bootstrap), not by query, and use a paired cluster bootstrap for comparisons.
- Report recall@k next to its ceiling (the best recall@k achievable given gold-set sizes), and also normalized recall@k = hits@k / min(k, |gold|).
- Report `subcat` and `example` queries separately as well as combined.

**Phases 4 and 5**
- Metric definitions are pre-registered in `DECISIONS.md`. Changing one after seeing results requires a new row with the reason.
- QA set: 60 answerable + 40 unanswerable questions. The agent drafts them and Jude labels them. Split 50/50 with a sealed test half.
- Phase 4 uses solo rubric judging. Phase 5 adds pairwise judging in both orders; a win counts only if it holds in both orders.
- The judge comes from a different model family than the generator if Jude provides a key. Otherwise, self-preference bias goes in the limitations.
- Cache every LLM response (and reranker scores) on disk so reruns are exact.
- The CI regression gate covers hybrid retrieval only, with no reranker model in CI.

**Teaching corrections**
- Phase 2 above says Postgres FTS has "no IDF saturation". The accurate version: BM25 multiplies IDF by a saturating term-frequency curve (k1) and normalizes for document length (b). Postgres `ts_rank` and `ts_rank_cd` use no corpus statistics at all (so no IDF), have no BM25-style saturation, and normalize for length only when asked to through their normalization flag. Teach this version.

## Amendments agreed on 2026-11-01

These override the text above, including the 2026-10-23 amendments, wherever they conflict. Each one has a row with its evidence in `DECISIONS.md`.

- **The Phase 6 UI is a full web app, not the minimal stretch item.** Build it in Phase 6, after the agent and the FastAPI endpoints exist: Next.js, in a modern brutalist style, following Jude's React conventions. Pages:
  - controls: browse and search the catalog;
  - configs: every setup we tested and which one production uses, plus live knobs for the retriever, the chunking strategy, k and the reranker;
  - results: every metric with its CI, and charts;
  - ask: a cited answer or a refusal;
  - trace: what the agent did for a question, step by step.
- The frontend has no typed numbers. It reads everything from `results/` or the API, as the docs do.
