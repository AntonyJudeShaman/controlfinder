.PHONY: up down reset-db schema psql test ann-demo ingest goldset embed baselines ablations qa generate eval agent-eval final-test ci-fixture ci-load ci-baseline ci-gate api web report docs

up: .env
	docker compose up -d --wait
	$(MAKE) schema

.env:
	cp .env.example .env

down:
	docker compose down

# Deletes the database volume. Needed after changing a column in schema.sql.
reset-db:
	docker compose down -v
	$(MAKE) up

schema:
	uv run python -m controlfinder.index.db

psql:
	docker compose exec db psql -U controlfinder controlfinder

test:
	uv run pytest -q

ann-demo:
	uv run python -m controlfinder.index.ann_filter_demo
	$(MAKE) docs

# Replaces the controls and chunks tables, including any embeddings.
ingest:
	uv run python -m controlfinder.ingest
	$(MAKE) docs

# Rebuilds data/eval/queries.jsonl (answer key, queries, dev/test split) from the committed xlsx.
goldset:
	uv run python -m controlfinder.eval.goldset
	$(MAKE) docs

# Embeds every chunk. Re-run after every `make ingest`.
embed:
	uv run python -m controlfinder.index.embed

baselines:
	uv run python -m controlfinder.eval.baselines
	$(MAKE) docs

# Reranker scores come from data/cache/rerank.jsonl; pairs not in it download and run the model.
ablations:
	uv run python -m controlfinder.eval.ablations
	$(MAKE) docs

# Checks the hand-labelled data/eval/qa.jsonl and writes data/eval/qa_review.md for reviewing it.
qa:
	uv run python -m controlfinder.eval.qa

# Answers and judge scores come from data/cache/llm.jsonl; calls not in it need CURSOR_API_KEY.
generate:
	uv run python -m controlfinder.eval.generation
	$(MAKE) docs

eval: goldset embed baselines ablations qa generate

# Sweeps τ, then compares the pipeline, the pipeline with base text and the agent on dev.
# Model calls and reranker scores come from data/cache/; calls not in it need CURSOR_API_KEY.
agent-eval:
	uv run python -m controlfinder.eval.agent
	$(MAKE) docs

# The one run on the sealed test split (Phase 6). Refuses to start once results/final_test.json exists.
final-test:
	CONTROLFINDER_UNSEAL_TEST=1 uv run python -m controlfinder.eval.final_test
	$(MAKE) docs

# The CI regression gate. ci-fixture needs the embedding model and a database after `make embed`;
# CI itself runs ci-load (after schema and ingest) and ci-gate, with no model download.
ci-fixture:
	uv run python -m controlfinder.eval.ci fixture

ci-load:
	uv run python -m controlfinder.eval.ci load

ci-baseline:
	uv run python -m controlfinder.eval.ci baseline

ci-gate:
	uv run python -m controlfinder.eval.ci gate

# The API on http://127.0.0.1:8000. /ask calls a model unless data/cache/llm.jsonl has the prompt.
api:
	uv run uvicorn controlfinder.api.app:app --port 8000

# The app on http://localhost:3000. It talks to `make api`, so start that first.
web:
	cd web && pnpm install --frozen-lockfile && pnpm build && pnpm start

# p50/p95 latency per stage and the abstention rate, per pipeline, from query_log.
report:
	uv run python -m controlfinder.obs.report

# Regenerates every results table in docs/learn/*.md and README.md.
docs:
	uv run python -m controlfinder.docgen
