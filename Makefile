.PHONY: up down reset-db schema psql test ann-demo ingest goldset embed baselines eval docs

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

eval: goldset embed baselines

# Regenerates every results table in docs/learn/*.md and README.md.
docs:
	uv run python -m controlfinder.docgen
