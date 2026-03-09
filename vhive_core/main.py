"""
Entry point to execute the LangGraph AURA workflow.
Run from project root: python -m vhive_core.main
Or: cd vhive_core && python main.py (with PYTHONPATH=..)
"""

import argparse
import logging
import logging.handlers
import sys
from pathlib import Path

VHIVE_HOME = Path.home() / ".vhive"
LOG_DIR = VHIVE_HOME / "logs"


def _setup_logging(log_to_file: bool = False) -> None:
    """Configure root logger: always stdout, optionally rotating file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Stdout handler
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    if log_to_file:
        # Rotating: 10 MB per file, keep 7 files (~70 MB max)
        fh = logging.handlers.RotatingFileHandler(
            LOG_DIR / "vhive.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=7,
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)

    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "uvicorn.access", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

# Ensure project root is on path when running as script
if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from dotenv import load_dotenv

# Load .env from vhive_core or project root
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")


def main():
    parser = argparse.ArgumentParser(description="Vhive AURA - Local Autonomous Agentic Workflow")
    parser.add_argument(
        "--trigger",
        choices=["full", "research"],
        default="full",
        help="Trigger mode: full (default) runs entire workflow, research runs research node only (cron-friendly)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check Ollama connectivity and exit",
    )
    parser.add_argument(
        "--server",
        action="store_true",
        help="Start FastAPI server with /ws WebSocket (Star-Office-UI backend)",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Start FastAPI server with built-in scheduler (24/7 autonomous mode)",
    )
    parser.add_argument(
        "--schedule-hours",
        type=float,
        default=None,
        help="Override schedule interval in hours (default: 6, or VHIVE_SCHEDULE_HOURS env var)",
    )
    args = parser.parse_args()

    if args.server or args.daemon:
        import os
        import uvicorn

        if args.daemon:
            os.environ["VHIVE_DAEMON"] = "1"
        if args.schedule_hours:
            os.environ["VHIVE_SCHEDULE_HOURS"] = str(args.schedule_hours)

        _setup_logging(log_to_file=True)
        log = logging.getLogger("vhive")

        port = int(os.environ.get("VHIVE_PORT", "8080"))
        mode = "daemon" if args.daemon else "server"

        from vhive_core.auth import API_KEY, KEY_FILE

        log.info("Starting Vhive in %s mode on port %d", mode, port)
        log.info("Logs: %s", LOG_DIR / "vhive.log")
        print(f"Starting Vhive in {mode} mode on port {port}")
        print(f"API key: {API_KEY}")
        print(f"  (stored in {KEY_FILE})")
        print(f"  Set VHIVE_API_KEY env var to override")
        print(f"  Logs: {LOG_DIR / 'vhive.log'}")
        try:
            from vhive_core.app import app
            uvicorn.run(app, host="0.0.0.0", port=port)
        except Exception:
            uvicorn.run("vhive_core.app:app", host="0.0.0.0", port=port)
        return None

    if args.check:
        from vhive_core.core.llm_config import check_ollama_connectivity

        ok = check_ollama_connectivity()
        print("Ollama: OK" if ok else "Ollama: NOT REACHABLE")
        sys.exit(0 if ok else 1)

    from vhive_core.core.graph import workflow

    if args.trigger == "research":
        # Cron-friendly: run only research node
        result = workflow.invoke(
            {"research_data": "", "errors": [], "retry_count": 0},
            config={"configurable": {"thread_id": "cron"}},
        )
    else:
        result = workflow.invoke(
            {"research_data": "", "errors": [], "retry_count": 0},
            config={"configurable": {"thread_id": "main"}},
        )

    print("Workflow result:", result)
    return result


if __name__ == "__main__":
    main()
