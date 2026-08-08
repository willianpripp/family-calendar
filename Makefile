# Operate the calendar on the `lab` guest from the workspace.
#
#   make deploy    # rsync this repo to the host, then up -d --build
#   make logs      # follow both containers
#   make psql      # a shell on the production database, so treat it as such
#
# The stack lives at /srv/lab/calendar on the guest and the Postgres data
# directory is bind-mounted there (homelab ADR-0005). That is the same path the
# homelab repo deployed to before this repo existed: splitting the code out
# moved nothing on the host.

HOST ?= lab
DIR  ?= /srv/lab/calendar

.PHONY: deploy up down restart status logs psql

# No --delete, deliberately. The host carries files git does not: `.env` (the
# database password and the TMDB key, mode 600) and any picture kept out of git
# for licensing. Deleting whatever is "missing" from the source would take
# those with it, and the .env is not recoverable from here.
deploy:
	rsync -a \
	  --exclude='.git/' --exclude='.gitignore' --exclude='__pycache__/' \
	  --exclude='Makefile' --exclude='README.md' --exclude='STATUS.md' \
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
