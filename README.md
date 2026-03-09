# VHIVE

## Autonomous Revenue Infrastructure for Digital Products

*Build. Deploy. Sell. Repeat — while you sleep.*

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-orange?style=flat-square)](https://langchain-ai.github.io/langgraph/)
[![CrewAI](https://img.shields.io/badge/CrewAI-1.10-purple?style=flat-square)](https://crewai.com)
[![Ollama](https://img.shields.io/badge/LLM-Local%20Ollama-black?style=flat-square)](https://ollama.ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

---

## Overview

Vhive is a fully local, self-hosted autonomous agent that runs a complete digital product business — market research, product creation, deployment, and sales outreach — on a configurable schedule, without human intervention.

The core persona is **AURA** (Autonomous User Acquisition & Revenue Agent). AURA wakes up every 6 hours, researches trending topics, builds a deployable digital product, ships it live on GitHub + Vercel with a Stripe payment link, then sends outreach via iMessage and Telegram. All LLM inference runs locally via Ollama — no OpenAI, no Anthropic, no external model costs.

---

## Architecture

Vhive is built on a strict three-layer "Tri-Force" design with clean separation between orchestration, execution, and infrastructure.

```text
┌─────────────────────────────────────────────────────────┐
│                   AURA Workflow Loop                    │
│                                                         │
│   Research → Build → Deploy → Outreach → Sleep → ...   │
└─────────────────────────────────────────────────────────┘
          │            │           │           │
    ┌─────▼─────┐ ┌────▼────┐ ┌───▼───┐ ┌────▼────┐
    │ Twitter   │ │  Dev    │ │GitHub │ │iMessage │
    │ Research  │ │ Agent   │ │Vercel │ │Telegram │
    │  Agent    │ │(qwen2.5)│ │Stripe │ │         │
    └───────────┘ └─────────┘ └───────┘ └─────────┘
          │            │
    ┌─────▼─────────────▼──────────────────────────┐
    │              Local Ollama                    │
    │   llama3.1:8b (creative) · qwen2.5-coder    │
    └──────────────────────────────────────────────┘
```

### Layer 1 — Orchestrator (LangGraph)

[vhive_core/core/graph.py](vhive_core/core/graph.py) defines a stateful directed graph with 5 nodes:

| Node | Function | Output |
| --- | --- | --- |
| `research` | Twitter trend analysis | Market insights |
| `product_build` | React+Vite landing page generation | JSON product bundle |
| `deploy` | GitHub → Vercel → Stripe pipeline | Live URL + payment link |
| `outreach` | iMessage + Telegram summaries | Delivery confirmations |
| `handle_error` | Retry logic (max 3 attempts) | Graceful degradation |

State flows through a `VhiveState` TypedDict. Every node reads from and writes to shared state. Errors trigger the retry handler; non-fatal failures return strings instead of raising, so the workflow always completes.

### Layer 2 — Workers (CrewAI)

[vhive_core/core/crews.py](vhive_core/core/crews.py) defines three specialized agents:

#### Twitter Research Analyst — `llama3.1:8b`, temp 0.7

Monitors Twitter for signals relevant to your products. Falls back to LLM training knowledge when API credits are exhausted. Writes new findings to persistent markdown memory.

#### Full-Stack Developer — `qwen2.5-coder:latest`, temp 0.1

Generates complete React+Vite landing pages as JSON bundles (index.html, package.json, App.tsx, PricingCard.tsx, vite.config.ts). Each page includes a Stripe payment button wired to a live payment link.

#### Sales Outreach Specialist — `llama3.1:8b`, temp 0.7

Sends a structured run summary to the operator via Telegram and iMessage after each completed cycle.

All agents use [LiteLLM](https://litellm.ai) to communicate with local Ollama — no external API keys required for inference.

### Layer 3 — Sandbox (Docker)

[vhive_core/fleet_manager.py](vhive_core/fleet_manager.py) manages ephemeral Docker containers:

```text
create container → inject code → execute → capture output → destroy
```

The `OpenHandsExecuteTool` wraps this lifecycle so the Dev Agent validates code before it ships.

---

## Deploy Pipeline

Every run, AURA attempts to ship a live product:

```text
JSON Bundle
    │
    ├─ 1. Stripe API  →  create Product + Price + Payment Link
    │                    inject live URL into buy button
    │
    ├─ 2. GitHub API  →  create repo + push all files via Git Data API
    │
    └─ 3. Vercel API  →  create project, link to GitHub repo,
                         trigger deploy, poll until READY,
                         return live URL
```

If any step fails (missing credentials, rate limits), AURA degrades gracefully and the workflow continues to outreach. Deploy status is logged to SQLite and surfaced in the Revenue dashboard.

---

## Real-Time UI — Star Office

The frontend ([frontend/](frontend/)) is a retro-futuristic "Star Office" dashboard built with React 18, TypeScript, and Tailwind CSS v4.

Three tabs:

- **Live** — WebSocket stream of agent thoughts, tool calls, and workflow state in real time
- **History** — All past runs with timing, status, step breakdown, and error messages
- **Revenue** — KPI cards (total revenue, orders, 24h), 30-day bar chart, per-product revenue table

The frontend builds to `vhive_core/static/` and is served same-origin from the FastAPI server on port 8080.

```text
ws://localhost:8080/ws?token=<api_key>   ← real-time event stream
http://localhost:8080                    ← Star Office UI
http://localhost:8080/health             ← health check
http://localhost:8080/docs               ← interactive API docs
```

---

## Memory System

AURA maintains three persistent memory layers in `~/.vhive/memory/`:

```text
~/.vhive/memory/
├── knowledge/areas/twitter-trends.md   ← what AURA has learned over time
├── daily/YYYY-MM-DD.md                 ← per-day activity logs
└── tacit/
    ├── rules.md                        ← hard constraints
    └── patterns.md                     ← verified contacts, outreach strategies
```

All memory is plain markdown — human-readable, editable, versionable. The Research Agent reads recent trend knowledge before each run and writes new findings back. The Outreach Agent reads tacit rules and patterns to guide every interaction.

---

## Getting Started

### Prerequisites

| Requirement | Version | Purpose |
| --- | --- | --- |
| Python | 3.11 – 3.13 | Backend runtime |
| [Ollama](https://ollama.ai) | Latest | Local LLM inference |
| Docker Desktop | Latest | Code execution sandbox |
| Node.js | 18+ | Frontend build |

### 1. Install Ollama models

```bash
ollama pull llama3.1:8b
ollama pull qwen2.5-coder
```

### 2. Clone and configure

```bash
git clone git@github.com:Radix-Obsidian/Vhive-.git
cd Vhive

cp vhive_core/.env.example vhive_core/.env
# Edit vhive_core/.env — see Environment Variables below
```

### 3. Install backend dependencies

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r vhive_core/requirements.txt
```

### 4. Build the frontend

```bash
cd frontend
npm install
npm run build:deploy   # outputs to vhive_core/static/
cd ..
```

### 5. Verify and launch

```bash
# Confirm Ollama is reachable
python -m vhive_core.main --check

# Run a single full workflow cycle
python -m vhive_core.main --trigger full

# Start the server (API + WebSocket + UI on port 8080)
python -m vhive_core.main --server

# Run as a 24/7 daemon scheduled every 6 hours
python -m vhive_core.main --daemon
```

### 6. (macOS) Install as a background service

```bash
mkdir -p ~/.vhive/logs
launchctl load ~/Desktop/Vhive/com.vhive.aura.plist
```

AURA will start at login, restart automatically on crash, and run every 6 hours.

---

## Environment Variables

Copy `vhive_core/.env.example` to `vhive_core/.env`.

| Variable | Required | Description |
| --- | --- | --- |
| `GITHUB_TOKEN` | Yes (deploy) | Fine-grained PAT with repo write + metadata read |
| `GITHUB_ORG` | No | Deploy repos to an org instead of personal account |
| `VERCEL_TOKEN` | Yes (deploy) | Vercel API token |
| `VERCEL_TEAM_ID` | No | Vercel team slug for team deployments |
| `STRIPE_SECRET_KEY` | Recommended | Enables real payment links and revenue tracking |
| `STRIPE_WEBHOOK_SECRET` | Recommended | Validates incoming Stripe order webhooks |
| `TWITTER_BEARER_TOKEN` | No | Twitter v2 search (improves research quality) |
| `TWITTER_API_KEY` | No | Twitter DM sending |
| `TWITTER_API_SECRET` | No | Twitter DM sending |
| `TWITTER_ACCESS_TOKEN` | No | Twitter DM sending |
| `TWITTER_ACCESS_TOKEN_SECRET` | No | Twitter DM sending |
| `TELEGRAM_BOT_TOKEN` | Recommended | Operator run summaries |
| `TELEGRAM_DEFAULT_CHAT_ID` | Recommended | Your Telegram chat ID |
| `VHIVE_API_KEY` | Auto | Override the auto-generated API key |
| `VHIVE_CORS_ORIGINS` | No | Comma-separated allowed origins (default: localhost:5174) |
| `VHIVE_PORT` | No | Server port (default: 8080) |

iMessage requires no keys — AURA uses macOS Messages.app via AppleScript. Sign into iMessage with your Apple ID on this Mac.

---

## API Reference

All endpoints except `/`, `/health`, and `/docs` require:

```text
Authorization: Bearer <api_key>
```

The API key is printed to the terminal on first server start and stored at `~/.vhive/api_key`.

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/health` | System health (DB, Ollama, scheduler, disk) |
| `POST` | `/run` | Trigger a full workflow run (409 if already running) |
| `POST` | `/demo` | Demo run with synthetic events — no Ollama required |
| `GET` | `/api/runs` | Paginated run history |
| `GET` | `/api/runs/{run_id}` | Single run with all step details |
| `GET` | `/api/stats` | Aggregate stats (total runs, success rate, avg duration) |
| `GET` | `/api/products` | All tracked products with per-product revenue |
| `GET` | `/api/revenue` | Revenue summary (totals, 24h/7d/30d, daily breakdown) |
| `POST` | `/api/revenue/sync` | Manually sync Stripe charges |
| `GET` | `/api/schedule` | Scheduler status and next run time |
| `POST` | `/api/schedule` | Update schedule interval |
| `GET` | `/api/memory/{layer}` | List memory files in a layer |
| `GET` | `/api/memory/{layer}/{filepath}` | Read a specific memory file |
| `GET` | `/api/memory-search` | Full-text search across all memory |
| `WS` | `/ws?token=<key>` | Real-time workflow event stream |

---

## Tech Stack

### Backend

- Python 3.11–3.13
- [FastAPI](https://fastapi.tiangolo.com) — HTTP server + WebSocket
- [LangGraph](https://langchain-ai.github.io/langgraph/) — stateful agent orchestration
- [CrewAI](https://crewai.com) 1.10 + [LiteLLM](https://litellm.ai) — multi-agent framework
- [Ollama](https://ollama.ai) — local LLM runtime (qwen2.5-coder, llama3.1:8b)
- [APScheduler](https://apscheduler.readthedocs.io) — background job scheduling
- SQLite (WAL mode) — run history, products, revenue events
- Docker SDK — ephemeral code execution sandbox

### Frontend

- React 18 + TypeScript
- Tailwind CSS v4
- Vite 6
- xterm.js — in-browser terminal
- WebSocket native API

### Integrations

- GitHub REST API (Git Data API) — repo creation + file push
- Vercel API — project creation + automated deployment
- Stripe API — payment links + revenue sync
- Twitter API v2 (Tweepy) — trend research + DMs
- Telegram Bot API — operator notifications
- macOS AppleScript (osascript) — iMessage

---

## Project Structure

```text
Vhive/
├── vhive_core/
│   ├── main.py               # CLI entry point (--server, --daemon, --trigger, --check)
│   ├── app.py                # FastAPI server + WebSocket
│   ├── auth.py               # API key generation and verification
│   ├── db.py                 # SQLite: runs, products, revenue events
│   ├── fleet_manager.py      # Docker container lifecycle
│   ├── memory.py             # Markdown memory system (PARA method)
│   ├── scheduler.py          # APScheduler + Stripe revenue sync
│   ├── stream_bus.py         # WebSocket event broadcaster
│   ├── core/
│   │   ├── graph.py          # LangGraph state machine (5 nodes)
│   │   ├── crews.py          # CrewAI agent and task definitions
│   │   └── llm_config.py     # Ollama LLM bindings via LiteLLM
│   ├── tools/
│   │   ├── github_tool.py    # GitHub repo creation + code push
│   │   ├── vercel_tool.py    # Vercel project deploy + polling
│   │   ├── twitter_tool.py   # Twitter search + DMs (Tweepy)
│   │   ├── telegram_tool.py  # Telegram Bot API
│   │   ├── imessage_tool.py  # macOS iMessage via AppleScript
│   │   └── openhands_tool.py # Docker sandbox code execution
│   └── static/               # Built frontend (served by FastAPI)
├── frontend/                 # React/TypeScript source
│   └── src/
│       ├── App.tsx
│       ├── auth.ts
│       ├── components/
│       │   ├── ThoughtStream.tsx
│       │   ├── WorkflowStatePanel.tsx
│       │   ├── TerminalPanel.tsx
│       │   ├── RunHistoryPanel.tsx
│       │   └── RevenueDashboard.tsx
│       ├── hooks/
│       │   ├── useVhiveApi.ts
│       │   └── useVhiveWebSocket.ts
│       └── types/vhive-ws.ts
├── com.vhive.aura.plist      # macOS launchd daemon config
├── CLAUDE.md                 # Developer guidance
└── README.md
```

---

## Data Persistence

| Store | Location | Contents |
| --- | --- | --- |
| SQLite DB | `~/.vhive/vhive.db` | Workflow runs, steps, products, revenue events |
| Memory | `~/.vhive/memory/` | Knowledge, daily logs, tacit rules (plain markdown) |
| API Key | `~/.vhive/api_key` | Auto-generated, 0o600 permissions |
| Logs | `~/.vhive/logs/` | Rotating log (10MB × 7 files = 70MB max) |
| Heartbeat | `~/.vhive/heartbeat` | Timestamp of last successful scheduler tick |

---

## Monitoring

```bash
# Confirm daemon is alive
launchctl list | grep vhive
cat ~/.vhive/heartbeat

# Health check
curl http://localhost:8080/health

# Last 5 workflow runs
sqlite3 ~/.vhive/vhive.db \
  "SELECT status, started_at FROM workflow_runs ORDER BY started_at DESC LIMIT 5;"

# Live log
tail -f ~/.vhive/logs/vhive.log
```

---

## Security

- **Authentication** — Single-user Bearer token, `secrets.token_urlsafe(32)`, auto-generated on first run
- **Timing safety** — `hmac.compare_digest` prevents timing-based key enumeration
- **CORS** — Configurable origin whitelist via `VHIVE_CORS_ORIGINS`
- **WebSocket auth** — Token passed as `?token=` query parameter
- **Secret hygiene** — `.env` excluded from version control; `.env.example` contains only safe placeholders
- **File permissions** — API key at `0o600` (owner read/write only)

---

## Roadmap

- [ ] Stripe webhook endpoint for real-time order notifications
- [ ] Multi-product portfolio analytics with conversion funnel
- [ ] Email outreach channel (SMTP / SendGrid)
- [ ] A/B landing page variants with revenue attribution
- [ ] Twitter API credit monitoring with automatic pause/resume
- [ ] Linux systemd service config
- [ ] Web-based memory editor in Star Office UI

---

## License

MIT — see [LICENSE](LICENSE).

---

Built to run autonomously. Designed to compound.

[Star Office UI](http://localhost:8080) · [API Docs](http://localhost:8080/docs) · [Health](http://localhost:8080/health)
