# Vhive Star-Office Client

Minimal React dashboard that connects to the Vhive FastAPI WebSocket (`/ws`) and displays:

- **Workflow state** – LangGraph node and state
- **Agent thoughts** – CrewAI streaming output (started / thought / finished)
- **Docker terminal** – stdout/stderr from sandbox execution

Theme: retro-futuristic “Star-Office” (dark background, amber/gold accents, monospace).

## Prerequisites

- Node.js 18+
- Vhive FastAPI backend running (see below)

## Setup

```bash
npm install
```

## Run

```bash
npm run dev
```

Opens at `http://localhost:5174`. The client connects to `ws://localhost:8000/ws` by default.

## Configuration

- **`VITE_VHIVE_WS_URL`** – WebSocket URL (default: `ws://localhost:8000/ws`). Set when the backend runs on another host/port.

  Example: create `.env` in this directory:

  ```env
  VITE_VHIVE_WS_URL=ws://localhost:8080/ws
  ```

## Running with the Vhive backend

1. **Start the backend** (from project root):

   ```bash
   # Default port 8080
   python -m vhive_core.main --server

   # Or port 8000 (matches client default)
   VHIVE_PORT=8000 python -m vhive_core.main --server
   ```

2. **Start this client:**

   ```bash
   cd star_office_ui/vhive-client && npm run dev
   ```

3. **Trigger the workflow:**  
   `POST http://localhost:8080/run` (or the port you used), or use the API docs at `http://localhost:8080/docs`.

Events stream over the WebSocket to the dashboard in real time.
