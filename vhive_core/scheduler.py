"""
AURA Scheduler — runs workflows on a configurable interval using APScheduler.
Integrates with the FastAPI lifespan and prevents overlapping runs.
Also syncs Shopify revenue data on a regular interval.
"""

import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger(__name__)

VHIVE_HOME = Path.home() / ".vhive"
HEARTBEAT_PATH = VHIVE_HOME / "heartbeat"

# Prevent two workflow runs from overlapping
_workflow_lock = threading.Lock()

# Module-level scheduler instance
scheduler: AsyncIOScheduler | None = None


def _write_heartbeat() -> None:
    """Write current UTC timestamp to heartbeat file."""
    VHIVE_HOME.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_PATH.write_text(datetime.now(timezone.utc).isoformat())


def _run_scheduled_workflow() -> None:
    """Execute the AURA workflow if no other run is in progress."""
    if not _workflow_lock.acquire(blocking=False):
        return  # Another run is active — skip this cycle

    try:
        # Import here to avoid circular imports at module load
        from vhive_core.app import _run_workflow

        _run_workflow(trigger_source="scheduled")
    except Exception:
        pass  # Errors are already logged by _run_workflow → db.end_run(status="failed")
    finally:
        _workflow_lock.release()


def run_workflow_with_lock(trigger_source: str = "manual") -> dict:
    """Run workflow with the global lock. Used by POST /run to prevent overlap."""
    if not _workflow_lock.acquire(blocking=False):
        raise RuntimeError("A workflow is already running. Please wait for it to finish.")

    try:
        from vhive_core.app import _run_workflow

        return _run_workflow(trigger_source=trigger_source)
    finally:
        _workflow_lock.release()


def sync_revenue() -> None:
    """Pull recent orders from Shopify, match to known products, record revenue events.

    Safe to call repeatedly — deduplicates on order GID.
    """
    try:
        from vhive_core.db import db
        from vhive_core.tools.shopify_tool import fetch_orders

        orders = fetch_orders(limit=50)
        new_events = 0
        for order in orders:
            if db.revenue_event_exists(order["id"]):
                continue  # Already recorded

            # Match line items to our tracked products
            for li in order.get("line_items", []):
                product_gid = li.get("product_id", "")
                if not product_gid:
                    continue
                product = db.get_product_by_shopify_gid(product_gid)
                if not product:
                    continue  # Not one of ours

                amount = li["price_cents"] * li.get("quantity", 1)
                db.add_revenue_event(
                    product_id=product["id"],
                    amount_cents=amount,
                    order_shopify_gid=order["id"],
                    currency=order.get("currency", "USD"),
                    customer_email=order.get("customer_email", ""),
                )
                new_events += 1

        if new_events:
            log.info("Revenue sync: recorded %d new events", new_events)
    except Exception as e:
        log.warning("Revenue sync failed: %s", e)


def create_scheduler(schedule_hours: float | None = None) -> AsyncIOScheduler:
    """Create and configure the scheduler (does not start it)."""
    global scheduler

    hours = schedule_hours or float(os.environ.get("VHIVE_SCHEDULE_HOURS", "6"))

    scheduler = AsyncIOScheduler()

    # Main workflow job
    scheduler.add_job(
        _run_scheduled_workflow,
        trigger=IntervalTrigger(hours=hours),
        id="aura_workflow",
        name="AURA Workflow",
        replace_existing=True,
    )

    # Revenue sync every 30 minutes
    scheduler.add_job(
        sync_revenue,
        trigger=IntervalTrigger(minutes=30),
        id="revenue_sync",
        name="Revenue Sync",
        replace_existing=True,
    )

    # Heartbeat every 60s
    scheduler.add_job(
        _write_heartbeat,
        trigger=IntervalTrigger(seconds=60),
        id="heartbeat",
        name="Heartbeat",
        replace_existing=True,
    )

    return scheduler


def get_schedule_info() -> dict:
    """Get current schedule state for the API."""
    if scheduler is None:
        return {"enabled": False}

    job = scheduler.get_job("aura_workflow")
    if job is None:
        return {"enabled": True, "next_run": None, "interval_hours": None}

    next_run = job.next_run_time
    trigger = job.trigger
    interval_hours = None
    if isinstance(trigger, IntervalTrigger):
        interval_hours = trigger.interval.total_seconds() / 3600

    # Read last heartbeat
    heartbeat = None
    if HEARTBEAT_PATH.exists():
        heartbeat = HEARTBEAT_PATH.read_text().strip()

    return {
        "enabled": scheduler.running,
        "next_run": next_run.isoformat() if next_run else None,
        "interval_hours": interval_hours,
        "last_heartbeat": heartbeat,
    }


def update_schedule(hours: float) -> dict:
    """Update the workflow interval at runtime."""
    if scheduler is None:
        raise RuntimeError("Scheduler not initialized")

    scheduler.reschedule_job(
        "aura_workflow",
        trigger=IntervalTrigger(hours=hours),
    )

    return get_schedule_info()
