"""
Star-Office-UI: FastAPI server with WebSocket streaming.
Wraps the LangGraph AURA workflow and streams state changes, agent thoughts,
and Docker terminal outputs to connected /ws clients.
Exposes API endpoints for run history, stats, and memory management.
"""

import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is on path
root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from vhive_core.auth import API_KEY, verify_key
from vhive_core.db import db
from vhive_core.memory import memory
from vhive_core.stream_bus import broadcaster

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Initialize memory directory structure on import
memory.init_memory()

# ── CORS origins (comma-separated, env var) ───────────────────
_raw_origins = os.environ.get("VHIVE_CORS_ORIGINS", "").strip()
CORS_ORIGINS: list[str] = (
    [o.strip() for o in _raw_origins.split(",") if o.strip()]
    if _raw_origins
    else [
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://100.96.209.87:5174",
        "https://bigmama.tail055222.ts.net",
    ]
)


# ── Auth dependency ───────────────────────────────────────────
from fastapi import HTTPException  # noqa: E402


async def require_api_key(request: Request) -> None:
    """Validate Bearer token on every protected request."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if verify_key(token, API_KEY):
            return
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _run_workflow(trigger_source: str = "manual") -> dict:
    """Run the AURA workflow (sync, for thread). Logs to DB and writes daily notes."""
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
    load_dotenv(Path(__file__).parent.parent / ".env")

    from vhive_core.core.graph import workflow

    # Start DB run
    run_id = db.start_run(trigger_source=trigger_source)

    broadcaster.emit_sync("workflow", {"event": "started", "run_id": run_id})

    final = {}
    error_msg = None
    try:
        for chunk in workflow.stream(
            {"run_id": run_id, "research_data": "", "errors": [], "retry_count": 0},
            config={"configurable": {"thread_id": f"run-{run_id}"}},
        ):
            for node_name, state in chunk.items():
                broadcaster.emit_sync("langgraph_state", {"node": node_name, "state": dict(state or {})})
            final = chunk
        db.end_run(run_id, status="completed")
        broadcaster.emit_sync("workflow", {"event": "completed", "run_id": run_id, "final_state": final})
    except Exception as e:
        error_msg = str(e)
        db.end_run(run_id, status="failed", error_message=error_msg)
        broadcaster.emit_sync("workflow", {"event": "error", "run_id": run_id, "message": error_msg})
        raise

    # Write daily note summarizing this run
    summary_parts = []
    for key in ("research_data", "product_code", "deployment_status", "outreach_drafts"):
        for node_state in (final.values() if isinstance(final, dict) else []):
            if isinstance(node_state, dict) and node_state.get(key):
                summary_parts.append(f"**{key}**: {str(node_state[key])[:300]}")
    if summary_parts:
        memory.write_daily_note(
            f"## Workflow Run `{run_id}` ({trigger_source})\n\n" + "\n\n".join(summary_parts)
        )

    return final


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Background task to drain event queue, broadcast to WebSockets, and optionally run scheduler."""
    stop = asyncio.Event()
    task = None

    async def drain_loop():
        while not stop.is_set():
            await broadcaster.drain_queue()
            await asyncio.sleep(0.05)

    task = asyncio.create_task(drain_loop())

    # Start scheduler if daemon mode is enabled
    _scheduler = None
    if os.environ.get("VHIVE_DAEMON") == "1":
        from vhive_core.scheduler import create_scheduler

        _scheduler = create_scheduler()
        _scheduler.start()

    yield

    # Shutdown
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    stop.set()
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Vhive Star-Office-UI", lifespan=lifespan)

# ── CORS middleware ───────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def root():
    """Serve the Star-Office dashboard."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("""
<!DOCTYPE html>
<html><head><title>Vhive</title></head><body>
<h1>Vhive Star-Office-UI</h1>
<p>Dashboard not found. Endpoints: <a href="/health">/health</a>, <a href="/docs">/docs</a></p>
</body></html>
""")


@app.get("/health")
async def health():
    """System health: DB, Ollama, scheduler, disk."""
    import asyncio

    checks: dict[str, object] = {}

    # 1. Database
    try:
        stats = db.get_stats()
        checks["db"] = {"ok": True, "runs": stats["total_runs"]}
    except Exception as e:
        checks["db"] = {"ok": False, "error": str(e)}

    # 2. Ollama
    try:
        import httpx

        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get("http://localhost:11434/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
            checks["ollama"] = {"ok": r.status_code == 200, "models": models}
    except Exception as e:
        checks["ollama"] = {"ok": False, "error": str(e)}

    # 3. Scheduler
    try:
        from vhive_core.scheduler import get_schedule_info

        info = get_schedule_info()
        checks["scheduler"] = {"ok": True, **info}
    except Exception as e:
        checks["scheduler"] = {"ok": False, "error": str(e)}

    # 4. Disk space at ~/.vhive
    try:
        import shutil

        usage = shutil.disk_usage(Path.home() / ".vhive")
        free_gb = usage.free / 1024**3
        checks["disk"] = {"ok": free_gb > 0.5, "free_gb": round(free_gb, 2)}
    except Exception as e:
        checks["disk"] = {"ok": False, "error": str(e)}

    all_ok = all(
        v.get("ok", False) if isinstance(v, dict) else True
        for v in checks.values()
    )
    return JSONResponse(
        status_code=200 if all_ok else 207,
        content={"status": "ok" if all_ok else "degraded", "checks": checks},
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = ""):
    """WebSocket with auth via ?token= query param."""
    if not token or not verify_key(token, API_KEY):
        await websocket.accept()
        await websocket.close(code=4401, reason="Unauthorized")
        return
    # broadcaster.connect calls websocket.accept()
    await broadcaster.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.disconnect(websocket)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=200,
        content={
            "message": "Vhive Star-Office-UI",
            "endpoints": {
                "health": "/health",
                "websocket": "/ws",
                "run_workflow": "POST /run",
                "runs": "GET /api/runs",
                "stats": "GET /api/stats",
                "revenue": "GET /api/revenue",
                "products": "GET /api/products",
                "revenue_sync": "POST /api/revenue/sync",
                "memory": "GET /api/memory/{layer}",
            },
        },
    )


# ── Workflow triggers ──────────────────────────────────────────


def _run_demo():
    """Emit fake events for UI testing - no dependencies required."""
    import time

    run_id = db.start_run(trigger_source="demo")
    broadcaster.emit_sync("workflow", {"event": "started", "mode": "demo", "run_id": run_id})
    time.sleep(0.5)
    broadcaster.emit_sync("crewai_agent", {"event": "started", "agent": "twitter_research"})
    time.sleep(0.8)
    broadcaster.emit_sync("crewai_agent", {"event": "finished", "agent": "twitter_research", "result_preview": "Trending: AI agents, digital products"})
    time.sleep(0.3)
    broadcaster.emit_sync("langgraph_state", {"node": "research", "state": {"research_data": "Demo research complete"}})
    time.sleep(0.5)
    broadcaster.emit_sync("crewai_agent", {"event": "started", "agent": "dev_product_build"})
    time.sleep(0.6)
    broadcaster.emit_sync("docker_terminal", {"stdout": "Hello from sandbox\n", "stderr": "", "exit_code": 0})
    time.sleep(0.4)
    broadcaster.emit_sync("crewai_agent", {"event": "finished", "agent": "dev_product_build"})
    time.sleep(0.3)
    db.end_run(run_id, status="completed")
    broadcaster.emit_sync("workflow", {"event": "completed", "mode": "demo", "run_id": run_id})

    # Write a demo daily note
    memory.write_daily_note(
        f"## Demo Run `{run_id}`\n\n"
        "**research_data**: Trending: AI agents, digital products\n\n"
        "**product_code**: Hello from sandbox"
    )


@app.post("/demo")
async def run_demo(_: None = Depends(require_api_key)):
    """Emit fake events for UI testing. No Ollama/CrewAI required."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_demo)
    return {"status": "demo_completed"}


@app.post("/run")
async def run_workflow(_: None = Depends(require_api_key)):
    """Trigger the AURA workflow. Events stream to /ws clients. Uses lock to prevent overlap."""
    from vhive_core.scheduler import run_workflow_with_lock

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, lambda: run_workflow_with_lock("api"))
        return {"status": "completed"}
    except RuntimeError as e:
        return JSONResponse(status_code=409, content={"status": "busy", "message": str(e)})
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── API: Run History & Stats ───────────────────────────────────


@app.get("/api/runs")
async def api_get_runs(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), _: None = Depends(require_api_key)):
    """Get recent workflow runs, newest first."""
    return db.get_runs(limit=limit, offset=offset)


@app.get("/api/runs/{run_id}")
async def api_get_run(run_id: str, _: None = Depends(require_api_key)):
    """Get a single run with its steps."""
    run = db.get_run_with_steps(run_id)
    if not run:
        return JSONResponse(status_code=404, content={"error": "Run not found"})
    return run


@app.get("/api/stats")
async def api_get_stats(_: None = Depends(require_api_key)):
    """Get aggregate workflow statistics."""
    return db.get_stats()


# ── API: Revenue & Products ────────────────────────────────────


@app.get("/api/revenue")
async def api_get_revenue(_: None = Depends(require_api_key)):
    """Get revenue summary: totals, 24h/7d/30d, daily breakdown."""
    return db.get_revenue_summary()


@app.get("/api/products")
async def api_get_products(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: None = Depends(require_api_key),
):
    """Get deployed products with aggregated revenue."""
    return db.get_products(limit=limit, offset=offset)


@app.post("/api/revenue/sync")
async def api_sync_revenue(_: None = Depends(require_api_key)):
    """Manually trigger a revenue sync from Shopify."""
    import asyncio

    from vhive_core.scheduler import sync_revenue

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, sync_revenue)
    return db.get_revenue_summary()


# ── API: Memory ────────────────────────────────────────────────


@app.get("/api/memory/{layer}")
async def api_list_memory(layer: str, subdir: str = Query("", description="Subdirectory within layer"), _: None = Depends(require_api_key)):
    """List files in a memory layer (knowledge, daily, tacit)."""
    files = memory.list_files(layer, subdir)
    if files is None:
        return JSONResponse(status_code=400, content={"error": f"Unknown layer: {layer}"})
    return {"layer": layer, "files": files}


@app.get("/api/memory/{layer}/{filepath:path}")
async def api_read_memory(layer: str, filepath: str, _: None = Depends(require_api_key)):
    """Read a specific memory file."""
    content = memory.read_file(layer, filepath)
    if content is None:
        return JSONResponse(status_code=404, content={"error": "File not found"})
    return {"layer": layer, "file": filepath, "content": content}


@app.put("/api/memory/{layer}/{filepath:path}")
async def api_write_memory(layer: str, filepath: str, request: Request, _: None = Depends(require_api_key)):
    """Write/update a memory file. Body should be JSON with a 'content' field."""
    body = await request.json()
    content = body.get("content", "")
    ok = memory.write_file(layer, filepath, content)
    if not ok:
        return JSONResponse(status_code=400, content={"error": "Invalid layer or path"})
    return {"status": "ok", "layer": layer, "file": filepath}


@app.get("/api/memory-search")
async def api_search_memory(q: str = Query(..., min_length=1), _: None = Depends(require_api_key)):
    """Search across all memory files."""
    results = memory.search_memory(q)
    return {"query": q, "results": results[:50]}


# ── API: Scheduler ─────────────────────────────────────────────


@app.get("/api/schedule")
async def api_get_schedule(_: None = Depends(require_api_key)):
    """Get current scheduler state: enabled, next run, interval."""
    from vhive_core.scheduler import get_schedule_info

    return get_schedule_info()


@app.post("/api/schedule")
async def api_update_schedule(request: Request, _: None = Depends(require_api_key)):
    """Update the workflow schedule interval. Body: { "hours": 4.0 }"""
    from vhive_core.scheduler import update_schedule

    body = await request.json()
    hours = body.get("hours")
    if not hours or not isinstance(hours, (int, float)) or hours <= 0:
        return JSONResponse(status_code=400, content={"error": "hours must be a positive number"})
    try:
        info = update_schedule(float(hours))
        return info
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("VHIVE_PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
