# Convenience targets. `make help` lists them.
#
# Postgres is started with pg_ctl rather than `brew services` because the
# launch agent only loads inside a GUI login session. If you want it to start
# automatically at login, run `brew services start postgresql@17` once from
# your own Terminal window.

PG_DATA := /opt/homebrew/var/postgresql@17
PG_LOG  := /opt/homebrew/var/log/postgresql@17.log
DB      := versioned_retrieval

# PostgreSQL refuses to start without a valid locale on macOS
# ("postmaster became multithreaded during startup").
export LC_ALL := en_US.UTF-8

.PHONY: help db-start db-stop db-status db-shell db-create migrate test

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

db-start: ## Start PostgreSQL
	pg_ctl -D $(PG_DATA) -l $(PG_LOG) start

db-stop: ## Stop PostgreSQL
	pg_ctl -D $(PG_DATA) stop

db-status: ## Is PostgreSQL accepting connections?
	pg_isready

db-shell: ## Open a psql shell on the project database
	psql -d $(DB)

db-create: ## Create the database and enable pgvector (first-time setup)
	createdb $(DB) || true
	psql -d $(DB) -c "CREATE EXTENSION IF NOT EXISTS vector;"

migrate: ## Apply any pending database migrations
	uv run python -m vre.migrate

test: ## Run the test suite
	uv run pytest -v
