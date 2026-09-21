# TINY (Reachy Mini) — operational verbs. `make help` for the full list.
# Mirrors neon-the-g1 / scout-the-rover Makefile conventions.

SHELL := /bin/bash
VENV  := .venv
PY    := $(VENV)/bin/python
PIP   := $(VENV)/bin/pip
COMPOSE := docker compose

.DEFAULT_GOAL := help

# ── env autoload ─────────────────────────────────────────────────────
ifneq (,$(wildcard .env))
include .env
export
endif

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── setup ─────────────────────────────────────────────────────────────
.PHONY: venv
venv: ## Create venv + install deps (bare-metal / dev)
	uv venv $(VENV) 2>/dev/null || python3 -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt
	-$(PIP) install -r requirements-robot.txt
	@echo "✓ venv ready → source $(VENV)/bin/activate"

# ── run (bare metal) ──────────────────────────────────────────────────
.PHONY: run run-bare ask sim
run: run-bare ## Alias for run-bare
run-bare: ## Run the REPL agent (needs the Reachy Mini daemon up)
	$(PY) agent.py

sim: ## Run REPL against MuJoCo simulation (no hardware)
	REACHY_USE_SIM=1 REACHY_SPAWN_DAEMON=1 $(PY) agent.py

ask: ## One-shot query:  make ask Q="say hi and wobble"
	@$(PY) -c "from tiny import build_shell_agent; a=build_shell_agent(); a('$(Q)')"

voice: ## Run the bidi voice listener (foreground)
	$(PY) voice_listener.py

tg: ## Run the telegram listener (foreground)
	$(PY) telegram_listener.py

thinker: ## Run the slow-thinker loop (foreground)
	$(PY) thinker_loop.py

# ── docker stack ──────────────────────────────────────────────────────
.PHONY: build up down logs exec ps restart
build: ## docker compose build
	$(COMPOSE) build

up: ## docker compose up -d (voice + telegram + thinker)
	$(COMPOSE) up -d

down: ## docker compose down
	$(COMPOSE) down

logs: ## Follow all container logs
	$(COMPOSE) logs -f

logs-voice: ## Follow voice logs
	$(COMPOSE) logs -f tiny-voice

logs-thinker: ## Follow thinker logs
	$(COMPOSE) logs -f tiny-thinker

exec: ## Shell into the voice container
	$(COMPOSE) exec tiny-voice bash

ps: ## Show container status
	$(COMPOSE) ps

restart: ## Restart the whole stack
	$(COMPOSE) restart

# ── systemd (boot persistence) ────────────────────────────────────────
.PHONY: install-compose-service install-bare-services
install-compose-service: ## Install the docker-compose boot unit (user systemd)
	mkdir -p ~/.config/systemd/user
	cp scripts/systemd/tiny-compose.service ~/.config/systemd/user/
	loginctl enable-linger "$$USER" || true
	systemctl --user daemon-reload
	systemctl --user enable --now tiny-compose.service
	@echo "✓ tiny-compose.service enabled — stack boots on power-on"

install-bare-services: ## Install per-persona bare-metal units (user systemd, needs venv)
	mkdir -p ~/.config/systemd/user
	cp scripts/systemd/tiny-voice.service ~/.config/systemd/user/
	cp scripts/systemd/tiny-telegram.service ~/.config/systemd/user/
	cp scripts/systemd/tiny-thinker.service ~/.config/systemd/user/
	loginctl enable-linger "$$USER" || true
	systemctl --user daemon-reload
	systemctl --user enable --now tiny-voice.service tiny-telegram.service tiny-thinker.service
	@echo "✓ bare-metal persona units enabled"

service-status: ## Show systemd unit status
	systemctl --user status tiny-*.service --no-pager || true

# ── voice control (live) ──────────────────────────────────────────────
.PHONY: mute unmute voice-status
mute: ## Mute the voice agent
	$(PY) -c "from tools.memory import memory; print(memory(action='kv_set', key='voice.muted', value='true'))"

unmute: ## Unmute the voice agent
	$(PY) -c "from tools.memory import memory; print(memory(action='kv_set', key='voice.muted', value='false'))"

voice-status: ## Show voice mute state
	$(PY) -c "from tools.memory import memory; print('muted=', memory(action='kv_get', key='voice.muted'))"

# ── memory / log inspection ───────────────────────────────────────────
.PHONY: log-show
log-show: ## Last 30 cross-persona turns
	$(PY) -c "from tools.agent_log import format_for_prompt; print(format_for_prompt(limit=30))"

# ── tests ─────────────────────────────────────────────────────────────
.PHONY: test test-tools
test: ## Run the test suite (no robot needed — uses sim/mocks)
	$(PY) -m pytest tests/ -v || $(PY) tests/test_import.py

budget: ## Docs word budget — per page + site (tools/docs_budget.py, CI gate)
	$(PY) tools/docs_budget.py

test-tools: ## Verify all tools import + register cleanly
	$(PY) tests/test_import.py
