# Atajos: make <objetivo>. Requiere haber ejecutado `make install` (o scripts/install.sh).
PY := .venv/bin/python
SYMBOL ?= BTC/USDT
SINCE ?= 2022-01-01

.PHONY: help install setup check test run status export kill resume backtest walkforward docker-check docker-up docker-down docker-logs docker-status

help:
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'

install: ## crea .venv, instala dependencias, pasa los tests y lanza el asistente
	./scripts/install.sh
setup: ## asistente de configuración (config.yaml + .env)
	$(PY) -m bot setup
check: ## comprobación previa (conexión, claves, mínimos, alertas)
	$(PY) -m bot check
test: ## tests
	$(PY) -m pytest -q
run: ## arranca el bot en primer plano
	$(PY) -m bot run
status: ## estado, posiciones y últimas operaciones
	$(PY) -m bot status
export: ## exporta las operaciones a data/operaciones.csv
	$(PY) -m bot export
kill: ## parada de emergencia: cierra todo y deja de operar
	$(PY) -m bot kill
resume: ## quita el kill switch
	$(PY) -m bot resume
backtest: ## backtest (SYMBOL=..., SINCE=...)
	$(PY) -m bot backtest --symbol $(SYMBOL) --since $(SINCE)
walkforward: ## validación walk-forward (SYMBOL=..., SINCE=...)
	$(PY) -m bot walkforward --symbol $(SYMBOL) --since $(SINCE)
docker-check: ## comprobación previa dentro de Docker
	@test -f config.yaml || { echo "Falta config.yaml: ejecuta make setup o copia config.example.yaml"; exit 1; }
	@test -f .env || cp .env.example .env
	mkdir -p data && docker compose build && BOT_UID=$$(id -u) BOT_GID=$$(id -g) docker compose run --rm bot python -m bot check
docker-up: ## arranca en Docker en segundo plano (reinicio automático)
	@test -f config.yaml || { echo "Falta config.yaml: ejecuta make setup o copia config.example.yaml"; exit 1; }
	@test -f .env || cp .env.example .env
	mkdir -p data && BOT_UID=$$(id -u) BOT_GID=$$(id -g) docker compose up -d --build
docker-down: ## para el contenedor (las posiciones se conservan)
	docker compose down
docker-logs: ## sigue los logs del contenedor
	docker compose logs -f
docker-status: ## estado del bot dentro de Docker
	docker compose exec bot python -m bot status
