# Vhive - Local Autonomous Agentic Workflow

A fully local AI workforce orchestrated by LangGraph, using CrewAI for multi-agent tasks and OpenHands for sandboxed code execution. The initial agent, AURA, drives cold traffic to digital products via Shopify, Twitter, iMessage, and Telegram.

## Requirements

- **Python 3.11, 3.12, or 3.13** (CrewAI does not support Python 3.14 yet)
- **Ollama** running locally with models: `qwen2.5-coder`, `llama3`
- **Docker** (optional, for OpenHands sandbox; falls back to local Python if unavailable)

## Setup

```bash
# Create virtual environment with Python 3.11-3.13
python3.12 -m venv .venv  # or python3.11, python3.13
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r vhive_core/requirements.txt

# Copy and configure environment
cp vhive_core/.env.example vhive_core/.env
# Edit vhive_core/.env with your API keys
```

## Configuration

Edit `vhive_core/.env` with:

- **Shopify:** `SHOPIFY_SHOP_DOMAIN`, `SHOPIFY_ACCESS_TOKEN`
- **Twitter:** `TWITTER_BEARER_TOKEN` (search); for DMs: `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_TOKEN_SECRET`
- **Telegram:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_DEFAULT_CHAT_ID`
- **iMessage:** No keys — sign into Messages.app with Apple ID

## Run

```bash
# From project root
python -m vhive_core.main

# Check Ollama connectivity
python -m vhive_core.main --check

# Cron-friendly (runs full workflow; starts at research)
python -m vhive_core.main --trigger research

# Star-Office-UI: Dashboard + WebSocket streaming
python -m vhive_core.main --server
# Backend: http://localhost:8080 (or VHIVE_PORT=8000 for port 8000)
# To see the live dashboard, run the Star-Office frontend:
#   cd star_office_ui/vhive-client && npm install && npm run dev
# Then open http://localhost:5174 and trigger the workflow via POST /run (or use API docs at /docs).
```

## Architecture

- **LangGraph** – Orchestrator (state machine, fail-safes)
- **CrewAI** – Multi-agent workers (Twitter, Dev, Sales)
- **Tools** – Shopify (GraphQL), Twitter (Tweepy), iMessage (AppleScript), Telegram (Bot API), fleet_manager (Docker SDK)
- **Star-Office-UI** – FastAPI + `/ws` WebSocket streams LangGraph state, agent thoughts, Docker terminal

See [vhive_architecture.md](vhive_architecture.md) for the full Master Implementation Document.
