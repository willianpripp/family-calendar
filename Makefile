# Operate the calendar on the deploy host from the workspace.
#
#   make demo      # try it locally: build, start, load a demo month
#   make deploy    # rsync this repo to the host, then up -d --build
#   make logs      # follow both containers
#   make psql      # a shell on the production database, so treat it as such
#
# The stack lives at a fixed path on the deploy host and the Postgres data
# directory is bind-mounted there. Splitting the app out of the broader
# household infrastructure repo moved nothing about that arrangement.

HOST ?= lab
DIR  ?= /srv/lab/calendar

.PHONY: deploy up down restart status logs psql demo demo-reset

# --- try it locally ---------------------------------------------------------
# `cp .env.example .env`, then `make demo`: the stack comes up on
# http://127.0.0.1:3002 with a plausible month already on the calendar.

demo:
	docker compose up -d --build
	@echo "waiting for the database…"
	@until docker compose exec -T db pg_isready -U calendar >/dev/null 2>&1; do sleep 1; done
	@sleep 2
	docker compose exec -T db psql -q -U calendar -d calendar < demo/seed.sql
	@echo "seeded. http://127.0.0.1:3002"

demo-reset:
	docker compose exec -T db psql -q -U calendar -d calendar \
	  -c "truncate events, reminders_sent restart identity cascade;"
	docker compose exec -T db psql -q -U calendar -d calendar < demo/seed.sql
	@echo "reseeded. http://127.0.0.1:3002"

# --- the household instance --------------------------------------------------

# No --delete, deliberately. The host carries files git does not: `.env` (the
# database password and the TMDB key, mode 600) and any picture kept out of git
# for licensing. Deleting whatever is "missing" from the source would take
# those with it, and the .env is not recoverable from here.
deploy:
	rsync -a \
	  --exclude='.git/' --exclude='.gitignore' --exclude='__pycache__/' \
	  --exclude='Makefile' --exclude='README.md' --exclude='STATUS.md' \
	  --exclude='LICENSE' --exclude='.env.example' --exclude='demo/' \
	  --exclude='docs/' --exclude='OBJECTIVES.md' \
	  ./ $(HOST):$(DIR)/
	ssh $(HOST) 'cd $(DIR) && docker compose up -d --build'

up:
	ssh $(HOST) 'cd $(DIR) && docker compose up -d'

down:
	ssh $(HOST) 'cd $(DIR) && docker compose down'

restart:
	ssh $(HOST) 'cd $(DIR) && docker compose restart'

status:
	ssh $(HOST) 'cd $(DIR) && docker compose ps'

logs:
	ssh $(HOST) 'cd $(DIR) && docker compose logs --tail=100 -f'

# There are real household events in here. Read freely; write with the same
# care you would give any production database.
psql:
	ssh -t $(HOST) 'cd $(DIR) && docker compose exec db psql -U calendar calendar'
