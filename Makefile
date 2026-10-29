.PHONY: up down reset-db schema psql test ann-demo docs

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

# Regenerates every results table in docs/learn/*.md and README.md.
docs:
	uv run python -m controlfinder.docgen
