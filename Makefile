# Common tasks, so nobody has to remember two toolchains.
#
#   make setup    once, after cloning
#   make dev      what to run every day (two terminals)
#   make check    everything CI would run

BACKEND  := backend
FRONTEND := frontend
API_PORT := 8010
WEB_PORT := 3111

.DEFAULT_GOAL := help

# ---------------------------------------------------------------- setup

.PHONY: setup
setup: setup-backend setup-frontend ## Install everything and create the database
	@echo ""
	@echo "Ready. Run 'make api' in one terminal and 'make web' in another."

.PHONY: setup-backend
setup-backend:
	cd $(BACKEND) && uv sync
	cd $(BACKEND) && uv run alembic upgrade head
	@test -f $(BACKEND)/.env || cp $(BACKEND)/.env.example $(BACKEND)/.env

.PHONY: setup-frontend
setup-frontend:
	cd $(FRONTEND) && npm install

# ---------------------------------------------------------------- run

.PHONY: api
api: ## Run the backend (http://127.0.0.1:8010)
	cd $(BACKEND) && uv run uvicorn app.main:app --port $(API_PORT) --reload

.PHONY: web
web: ## Run the frontend (http://localhost:3111)
	@# localhost, not 127.0.0.1: Next treats them as different origins and
	@# blocks its own dev resources across them, which breaks hydration.
	cd $(FRONTEND) && npm run dev -- --port $(WEB_PORT)

.PHONY: ready
ready: ## Is the backend healthy, and which provider is it using?
	@curl -s http://127.0.0.1:$(API_PORT)/health/ready | python3 -m json.tool

# ---------------------------------------------------------------- test

.PHONY: check
check: test-backend test-frontend lint types ## Everything CI would run

.PHONY: test
test: test-backend test-frontend ## Backend and frontend unit tests

.PHONY: test-backend
test-backend:
	cd $(BACKEND) && uv run pytest

.PHONY: test-frontend
test-frontend:
	cd $(FRONTEND) && npm test

.PHONY: e2e
e2e: ## End-to-end journey — needs both servers running, backend on the fake provider
	cd $(FRONTEND) && npm run e2e

.PHONY: lint
lint: ## Lint the frontend
	cd $(FRONTEND) && npx eslint src --max-warnings 0

.PHONY: types
types: ## Type-check the frontend
	cd $(FRONTEND) && npx tsc --noEmit

.PHONY: api-types
api-types: ## Regenerate the frontend's API types from the running backend
	cd $(FRONTEND) && npm run types

# ---------------------------------------------------------------- database

.PHONY: migrate
migrate: ## Apply migrations
	cd $(BACKEND) && uv run alembic upgrade head

.PHONY: migration
migration: ## Create a migration from model changes: make migration m="add x"
	@test -n "$(m)" || (echo "usage: make migration m=\"what changed\"" && exit 1)
	@# Against an EMPTY database on purpose. Autogenerate diffs the models
	@# against whatever DATABASE_URL points at, so running it against a
	@# database that is already up to date produces a migration containing
	@# `pass` — and a fresh deploy then creates no schema at all.
	cd $(BACKEND) && rm -f /tmp/fs-autogen.db && \
		DATABASE_URL=sqlite:////tmp/fs-autogen.db uv run alembic upgrade head >/dev/null && \
		DATABASE_URL=sqlite:////tmp/fs-autogen.db uv run alembic revision --autogenerate -m "$(m)"

.PHONY: db
db: ## Open the database in DB Browser
	open -a "DB Browser for SQLite" $(BACKEND)/flight_system.db

.PHONY: fixtures
fixtures: ## Record a real API response: make fixtures f=LY315 d=2026-09-14
	@test -n "$(f)" -a -n "$(d)" || (echo "usage: make fixtures f=LY315 d=2026-09-14" && exit 1)
	cd $(BACKEND) && uv run python scripts/record_fixtures.py $(f) $(d)

# ---------------------------------------------------------------- misc

.PHONY: help
help:
	@grep -hE '^[a-z0-9-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
