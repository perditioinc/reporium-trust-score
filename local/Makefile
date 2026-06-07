# Local OSS dev substrate for reporium-trust-score.
# $0 / OSS / ADDITIVE / local only. Never touches production cloud.

COMPOSE ?= docker compose
PY      ?= python

.PHONY: help up down seed smoke logs ps clean

help:
	@echo "Reporium trust-score local substrate targets:"
	@echo "  make up     - build + start stub + postgres (waits for healthy)"
	@echo "  make seed   - (re)apply the graph-quality seed into postgres"
	@echo "  make smoke  - run probes against the local stub + compute a score"
	@echo "  make down   - stop and remove containers + volumes (-v)"
	@echo "  make logs   - tail substrate logs"
	@echo "  make ps     - show substrate container status"

up:
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) down -v

# The seed auto-runs on first DB init via docker-entrypoint-initdb.d. This
# target re-applies it on demand (e.g. after editing seed/graph_quality.sql)
# without recreating the volume.
seed:
	$(COMPOSE) exec -T db psql -U reporium -d reporium < seed/graph_quality.sql

smoke:
	REPORIUM_API_BASE=http://localhost:8080 \
	REPORIUM_HOME_URL=http://localhost:8080/ \
	REPORIUM_APP_TOKEN=local-dev-token \
	REPORIUM_ADMIN_KEY=local-dev-admin-key \
	REPORIUM_ASK_SLEEP_S=0 \
	$(PY) smoke.py

logs:
	$(COMPOSE) logs --tail=100

ps:
	$(COMPOSE) ps

clean: down
	@echo "substrate torn down"
