# VHIVE: Master Implementation Document (MID)

**Target Execution Agent:** Claude Code
**Project Name:** Vhive (Local Autonomous Agentic Workflow)
**Core Persona:** AURA (Autonomous User Acquisition & Revenue Agent)

## 1. Product Requirements Document (PRD)

**1.1 Objective**
Build "Vhive," a fully local, zero-compute-cost AI workforce operating entirely on a Mac (64GB RAM). Vhive orchestrates complex marketing and development tasks using local LLMs. The initial agent, AURA, is tasked with driving cold traffic to three domains (https://www.google.com/search?q=viperbyproof.com, complybyproof.com, itsvoco.com) by generating and selling digital products via Shopify, and conducting outreach via Twitter and WhatsApp.

**1.2 Core Capabilities**

* **Local LLM Routing:** All AI generation must be routed through a local Ollama instance. No OpenAI/Anthropic API calls for the core logic.
* **Stateful Orchestration:** Workflows must be cyclical and fault-tolerant, handling API failures gracefully without infinite loops.
* **Multi-Agent Collaboration:** Distinct personas (e.g., Copywriter, Python Dev, Strategist) must collaborate on sub-tasks.
* **Sandboxed Execution:** The agent must be able to write and execute code (e.g., node scripts, python scripts) in an isolated, safe environment to prevent host machine damage.
* **Omnichannel Integration:** Must seamlessly connect to Shopify Admin, Twitter v2, and WhatsApp Cloud APIs.

## 2. System Design Document (SDD)

Vhive relies on a strict "Tri-Force" architecture. Do not deviate from this hierarchy.

* **The Orchestrator (LangGraph):** The absolute top layer. LangGraph dictates the state, memory, and flow of the program. It acts as the failsafe.
* **The Workers (CrewAI):** LangGraph nodes will trigger specific CrewAI squads. CrewAI handles the multi-agent brainstorming and text generation.
* **The Sandbox (OpenHands):** CrewAI agents will be equipped with a custom tool that sends code/commands to an OpenHands (formerly OpenDevin) Docker container via its REST API for execution.

**2.1 Data Flow**

1. **Trigger:** Cron job or manual terminal execution starts the LangGraph workflow.
2. **State 1 (Research):** LangGraph calls CrewAI Twitter Agent -> Fetches trends via official Twitter API.
3. **State 2 (Product Build):** LangGraph passes research to CrewAI Dev Agent -> Agent writes code for a digital product -> Agent sends code to OpenHands Docker for compilation/testing.
4. **State 3 (Deployment):** OpenHands sandbox executes Shopify Admin API script to push the product live.
5. **State 4 (Outreach):** CrewAI Sales Agent drafts WhatsApp/Twitter DMs and executes them via respective APIs.

## 3. Technical Design Document (TDD) & Implementation Constraints

**Attention Claude Code:** You must strictly utilize the following official SDKs and repositories. **Do not build wrappers from scratch if an official SDK exists.**

**3.1 Tech Stack & Official Integrations**

* **Python Version:** Python 3.11+
* **LLM Interface:** `langchain-ollama` (Official LangChain integration for Ollama).
* **Orchestration:** `langgraph` (Build strict `StateGraph` workflows).
* **Multi-Agent:** `crewai` and `crewai[tools]`.
* **Code Sandbox:** Use the official OpenHands docker image (`docker pull docker.all-hands.dev/all-hands-ai/openhands:main`). Interface with it via its documented REST API or CLI hooks.
* **Shopify API:** `shopify-api-python` (Official Shopify Admin API library). Use GraphQL endpoints where possible for efficiency.
* **Twitter API:** `tweepy` (Standard, battle-tested library for Twitter API v2).
* **WhatsApp API:** Direct HTTP requests to the official `Meta Graph API v19.0+` (WhatsApp Cloud API endpoints).

**3.2 Directory Structure**
Construct the repository exactly as follows:

```text
vhive_core/
├── core/
│   ├── graph.py          # LangGraph state definitions and routing
│   ├── crews.py          # CrewAI agent and task definitions
│   └── llm_config.py     # Ollama Langchain bindings (qwen2.5-coder & llama3)
├── tools/
│   ├── openhands_tool.py # Custom tool connecting CrewAI to Docker sandbox (via fleet_manager)
│   ├── shopify_tool.py   # Shopify SDK integrations
│   ├── twitter_tool.py  # Tweepy integrations
│   └── whatsapp_tool.py  # Meta Graph API requests
├── fleet_manager.py     # ContainerManager: run(), execute(), stop() via Docker Python SDK
├── stream_bus.py        # Star-Office-UI: Event broadcaster for /ws WebSocket
├── app.py                # FastAPI server with /ws and /run
├── sandbox/              # Mounted volume for ephemeral containers
├── main.py               # Entry point (CLI + --server for FastAPI)
├── requirements.txt
└── .env                  # STRICTLY FOR API KEYS (No LLM keys needed, local only)
```

**3.3 Crucial Implementation Rules for Claude Code**

1. **Fail-Safes:** In `graph.py`, every node that makes an external API call (Shopify, Twitter, WhatsApp) MUST have a conditional edge mapped to an error-handling node. If an API rate limit is hit, the graph must pause and retry, not crash.
2. **Tool Creation:** When creating custom tools in `tools/`, use the `@tool` decorator from `langchain.tools` so they are fully compatible with CrewAI agents.
3. **Local LLM Binding:** In `llm_config.py`, point the LLM base URL strictly to `http://localhost:11434` (Ollama default). Set the temperature for coding tasks to `0.1` and creative tasks to `0.7`.
4. **OpenHands Bridging:** The `openhands_tool.py` must simply take string code from a CrewAI agent, write it to a file in the `sandbox/` directory, and trigger the OpenHands docker container to execute it and return the stdout/stderr.

**3.4 Execution Phase 1 Steps**

1. Initialize the Python environment and install the exact libraries specified.
2. Draft the `.env.example` file with placeholder keys for Shopify, Twitter, and WhatsApp.
3. Build `llm_config.py` to ensure local LLM connectivity.
4. Scaffold the `graph.py` state machine before filling in the CrewAI logic.

---

## 4. UI & Orchestration Layer (Star-Office-UI)

**4.1 Dynamic Container Fleet (The Local Orgo)**

Vhive must not rely on a single static sandbox. Implement the official Docker Python SDK to dynamically spawn ephemeral containers for code execution.

**Tools:** The `ContainerManager` class (in `fleet_manager.py`) provides:
- `run()` — Spin up an isolated Docker container (using `ubuntu:latest` or `node:alpine` images)
- `execute()` — Run a command or generated script inside the container and return stdout/stderr to the CrewAI agent
- `stop()` — Tear down the container

The helper `execute_in_container(code, language=...)` performs a one-shot run: create container, write code to a temp file, execute, tear down. It is used by `openhands_tool.py` to run agent-generated Python or JavaScript. The LangGraph orchestrator uses this fleet manager programmatically via CrewAI tools; each execution gets its own ephemeral container, and logs are streamed back to the agent and to the Star-Office-UI WebSocket.

**4.2 Frontend Architecture (Star-Office-UI)**

Wrap the LangGraph execution loop in a FastAPI application (`app.py`).

**Backend:**
- Implement a `/ws` WebSocket endpoint that streams in real-time:
  - LangGraph state changes (per-node state updates)
  - CrewAI agent thoughts (streaming chunks when `stream=True` on Crews)
  - Docker terminal outputs (stdout/stderr from containers via `openhands_tool`)

**4.2.1 Frontend Path A (OpenHands Fork)**

Fork the [OpenHands](https://github.com/all-hands-ai/openhands) repository and reskin the existing React frontend (chat + terminal + browser) with a retro-futuristic "Star-Office" theme.

- **WebSocket:** Configure the frontend WebSocket client to connect to Vhive FastAPI at `ws://localhost:8000/ws` (or configurable backend URL).
- **Event mapping:** Map Vhive event types to UI components:
  - `langgraph_state` → workflow/state panel
  - `crewai_agent` (event: `started` | `thought` | `finished`) → chat / agent thought stream
  - `docker_terminal` → live terminal (e.g. xterm.js) showing stdout/stderr
  - `workflow` (event: `started` | `completed` | `error`) → status bar or workflow indicator
- **Theme:** Apply Star-Office styling via Tailwind/CSS: dark background, amber/gold accents, monospace fonts, subtle scanlines or grid for a retro-futuristic look.

**4.2.2 Frontend Path B (Custom Next.js — Future Alternative)**

For total control, a custom Next.js dashboard can be built that consumes the same `/ws` endpoint. The backend contract remains unchanged; the frontend would be implemented from scratch with Tailwind CSS and the same event mapping as above.
