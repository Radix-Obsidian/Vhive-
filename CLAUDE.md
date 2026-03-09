# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vhive is a fully local, AI-powered autonomous agentic workflow. The core persona is AURA (Autonomous User Acquisition & Revenue Agent), which drives traffic to digital products via Shopify, Twitter, iMessage, and Telegram. It uses LangGraph for orchestration, CrewAI for multi-agent collaboration, and Docker for sandboxed code execution. All LLM inference is local via Ollama (no external LLM APIs).

## Commands

### Backend (Python)
```bash
source .venv/bin/activate
pip install -r vhive_core/requirements.txt

python -m vhive_core.main --check          # Check Ollama connectivity
python -m vhive_core.main --trigger full   # Run full workflow
python -m vhive_core.main --trigger research  # Run research node only
python -m vhive_core.main --server         # Start FastAPI server (default port 8080, set VHIVE_PORT to change)
```

### Frontend (React/TypeScript)
```bash
cd star_office_ui/vhive-client
npm install
npm run dev    # Dev server at http://localhost:5174
npm run build  # Production build to dist/
```

### Integration Testing
```bash
# Terminal 1: python -m vhive_core.main --server
# Terminal 2: cd star_office_ui/vhive-client && npm run dev
# Terminal 3: curl -X POST http://localhost:8080/run   (or /demo for fake events without Ollama)
```

## Architecture: "Tri-Force" Design

Three strict layers with clear separation:

1. **Orchestrator (LangGraph)** — `vhive_core/core/graph.py`
   - State machine with 5 nodes: research → product_build → deploy → outreach → END
   - Conditional edges route errors to `handle_error` node (max 3 retries)
   - State schema (`VhiveState`): research_data, product_code, deployment_status, outreach_drafts, errors, should_retry, retry_count

2. **Workers (CrewAI)** — `vhive_core/core/crews.py`
   - Twitter Research Agent (CREATIVE_LLM/llama3, temp 0.7) — searches trends
   - Python Developer Agent (CODING_LLM/qwen2.5-coder, temp 0.1) — writes & executes code in Docker
   - Sales Outreach Agent (CREATIVE_LLM, temp 0.7) — sends DMs via iMessage/Telegram/Twitter
   - Crews use `stream=True` to emit thoughts to WebSocket clients

3. **Sandbox (Docker)** — `vhive_core/fleet_manager.py`
   - Ephemeral containers (create → write code → execute → destroy)
   - `execute_in_container()` returns ExecutionResult with stdout/stderr/exit_code
   - Used by `OpenHandsExecuteTool` in `vhive_core/tools/openhands_tool.py`

## Real-Time Communication

- **Backend**: `StreamBroadcaster` (`stream_bus.py`) queues events from sync workflow code, drains to async WebSocket clients
- **Frontend**: `useVhiveWebSocket` hook connects to `ws://localhost:8000/ws`
- **Message types**: `workflow`, `langgraph_state`, `crewai_agent`, `docker_terminal` (defined in `src/types/vhive-ws.ts`)

## Key Files

| File | Role |
|------|------|
| `vhive_core/main.py` | CLI entry point (--server, --trigger, --check) |
| `vhive_core/app.py` | FastAPI server (/ws, /run, /demo, /health, /api/revenue, /api/products) |
| `vhive_core/core/graph.py` | LangGraph state machine |
| `vhive_core/core/crews.py` | CrewAI agent/task definitions |
| `vhive_core/core/llm_config.py` | Ollama LangChain bindings (CODING_LLM, CREATIVE_LLM) |
| `vhive_core/fleet_manager.py` | Docker container lifecycle |
| `vhive_core/stream_bus.py` | WebSocket event broadcaster |
| `vhive_core/tools/` | CrewAI tools: openhands, twitter, shopify, imessage, telegram |
| `vhive_core/auth.py` | API key generation, loading, verification |
| `star_office_ui/vhive-client/src/auth.ts` | Frontend token storage (localStorage) |
| `star_office_ui/vhive-client/src/App.tsx` | React main layout (3-panel: agent thoughts, workflow state, terminal) |

## LLM Configuration

Ollama must be running locally (`ollama serve` on localhost:11434). Required models:
- `qwen2.5-coder` — coding tasks (low temperature)
- `llama3` — creative tasks (higher temperature)

## Environment Variables

Copy `vhive_core/.env.example` to `vhive_core/.env`. Keys needed:
- **Shopify**: SHOPIFY_SHOP_DOMAIN, SHOPIFY_ACCESS_TOKEN
- **Twitter**: TWITTER_BEARER_TOKEN, TWITTER_API_KEY/SECRET, TWITTER_ACCESS_TOKEN/SECRET
- **Telegram**: TELEGRAM_BOT_TOKEN, TELEGRAM_DEFAULT_CHAT_ID
- **iMessage**: No keys — uses macOS Messages.app (must be signed in with Apple ID)
- **Server Security**: VHIVE_API_KEY (auto-generated at `~/.vhive/api_key` if unset), VHIVE_CORS_ORIGINS (comma-separated, defaults to localhost:5174)

## Tech Stack

- **Backend**: Python 3.11-3.13, FastAPI, LangGraph, CrewAI, langchain-ollama, Docker SDK, Tweepy
- **Frontend**: React 18, TypeScript, Tailwind CSS v4, Vite, xterm.js
- **Theme**: "Star-Office" retro-futuristic (dark bg #0a0a0c, amber accents #f59e0b)
