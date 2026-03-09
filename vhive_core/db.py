"""
SQLite persistence for Vhive workflow runs and steps.
Database stored at ~/.vhive/vhive.db — survives code updates.
"""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

VHIVE_HOME = Path.home() / ".vhive"
DB_PATH = VHIVE_HOME / "vhive.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class VhiveDB:
    """Lightweight SQLite wrapper for workflow run tracking."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._ensure_tables()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _ensure_tables(self) -> None:
        cur = self.conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS workflow_runs (
                id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                trigger_source TEXT DEFAULT 'manual',
                error_message TEXT
            );

            CREATE TABLE IF NOT EXISTS workflow_steps (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                node_name TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                output_summary TEXT,
                FOREIGN KEY (run_id) REFERENCES workflow_runs(id)
            );

            CREATE INDEX IF NOT EXISTS idx_steps_run ON workflow_steps(run_id);
            CREATE INDEX IF NOT EXISTS idx_runs_started ON workflow_runs(started_at);

            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                run_id TEXT,
                shopify_gid TEXT,
                title TEXT NOT NULL,
                product_type TEXT DEFAULT 'digital',
                price_cents INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES workflow_runs(id)
            );

            CREATE TABLE IF NOT EXISTS revenue_events (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                order_shopify_gid TEXT,
                amount_cents INTEGER NOT NULL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                customer_email TEXT,
                source TEXT DEFAULT 'shopify',
                event_at TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE INDEX IF NOT EXISTS idx_products_run ON products(run_id);
            CREATE INDEX IF NOT EXISTS idx_products_shopify ON products(shopify_gid);
            CREATE INDEX IF NOT EXISTS idx_revenue_product ON revenue_events(product_id);
            CREATE INDEX IF NOT EXISTS idx_revenue_event_at ON revenue_events(event_at);
        """)
        self.conn.commit()

    # ── Run lifecycle ──────────────────────────────────────────

    def start_run(self, trigger_source: str = "manual") -> str:
        """Create a new workflow run. Returns the run_id."""
        run_id = uuid.uuid4().hex[:12]
        self.conn.execute(
            "INSERT INTO workflow_runs (id, started_at, status, trigger_source) VALUES (?, ?, 'running', ?)",
            (run_id, _now(), trigger_source),
        )
        self.conn.commit()
        return run_id

    def end_run(self, run_id: str, status: str = "completed", error_message: str | None = None) -> None:
        """Mark a workflow run as completed or failed."""
        self.conn.execute(
            "UPDATE workflow_runs SET ended_at = ?, status = ?, error_message = ? WHERE id = ?",
            (_now(), status, error_message, run_id),
        )
        self.conn.commit()

    # ── Step logging ───────────────────────────────────────────

    def log_step_start(self, run_id: str, node_name: str) -> str:
        """Log the start of a workflow step. Returns step_id."""
        step_id = uuid.uuid4().hex[:12]
        self.conn.execute(
            "INSERT INTO workflow_steps (id, run_id, node_name, started_at, status) VALUES (?, ?, ?, ?, 'running')",
            (step_id, run_id, node_name, _now()),
        )
        self.conn.commit()
        return step_id

    def log_step_end(self, step_id: str, status: str = "completed", output_summary: str | None = None) -> None:
        """Mark a workflow step as completed or failed."""
        self.conn.execute(
            "UPDATE workflow_steps SET ended_at = ?, status = ?, output_summary = ? WHERE id = ?",
            (_now(), status, output_summary, step_id),
        )
        self.conn.commit()

    # ── Queries ────────────────────────────────────────────────

    def get_runs(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """Get recent workflow runs, newest first."""
        rows = self.conn.execute(
            "SELECT * FROM workflow_runs ORDER BY started_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_run_with_steps(self, run_id: str) -> dict | None:
        """Get a single run with its steps."""
        row = self.conn.execute("SELECT * FROM workflow_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        run = dict(row)
        steps = self.conn.execute(
            "SELECT * FROM workflow_steps WHERE run_id = ? ORDER BY started_at",
            (run_id,),
        ).fetchall()
        run["steps"] = [dict(s) for s in steps]
        return run

    # ── Product tracking ──────────────────────────────────────

    def add_product(
        self,
        title: str,
        shopify_gid: str = "",
        run_id: str = "",
        product_type: str = "digital",
        price_cents: int = 0,
    ) -> str:
        """Register a deployed product. Returns the product_id."""
        product_id = uuid.uuid4().hex[:12]
        self.conn.execute(
            "INSERT INTO products (id, run_id, shopify_gid, title, product_type, price_cents, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'active', ?)",
            (product_id, run_id, shopify_gid, title, product_type, price_cents, _now()),
        )
        self.conn.commit()
        return product_id

    def get_products(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Get products newest first, with aggregated revenue."""
        rows = self.conn.execute(
            """
            SELECT p.*,
                   COALESCE(SUM(r.amount_cents), 0) AS total_revenue_cents,
                   COUNT(r.id) AS order_count
            FROM products p
            LEFT JOIN revenue_events r ON r.product_id = p.id
            GROUP BY p.id
            ORDER BY p.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_product_by_shopify_gid(self, shopify_gid: str) -> dict | None:
        """Look up a product by its Shopify GID."""
        row = self.conn.execute("SELECT * FROM products WHERE shopify_gid = ?", (shopify_gid,)).fetchone()
        return dict(row) if row else None

    # ── Revenue events ─────────────────────────────────────────

    def add_revenue_event(
        self,
        product_id: str,
        amount_cents: int,
        order_shopify_gid: str = "",
        currency: str = "USD",
        customer_email: str = "",
        source: str = "shopify",
    ) -> str:
        """Record a revenue event (sale). Returns event_id."""
        event_id = uuid.uuid4().hex[:12]
        self.conn.execute(
            "INSERT INTO revenue_events (id, product_id, order_shopify_gid, amount_cents, currency, customer_email, source, event_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, product_id, order_shopify_gid, amount_cents, currency, customer_email, source, _now()),
        )
        self.conn.commit()
        return event_id

    def revenue_event_exists(self, order_shopify_gid: str) -> bool:
        """Check if we already recorded this order (dedup)."""
        row = self.conn.execute(
            "SELECT 1 FROM revenue_events WHERE order_shopify_gid = ? LIMIT 1",
            (order_shopify_gid,),
        ).fetchone()
        return row is not None

    def get_revenue_summary(self) -> dict:
        """Aggregate revenue stats across all products."""
        cur = self.conn.cursor()

        total_revenue = cur.execute("SELECT COALESCE(SUM(amount_cents), 0) FROM revenue_events").fetchone()[0]
        total_orders = cur.execute("SELECT COUNT(*) FROM revenue_events").fetchone()[0]
        total_products = cur.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        active_products = cur.execute("SELECT COUNT(*) FROM products WHERE status = 'active'").fetchone()[0]

        # Revenue last 24h
        rev_24h = cur.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM revenue_events WHERE event_at >= datetime('now', '-1 day')"
        ).fetchone()[0]

        # Revenue last 7 days
        rev_7d = cur.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM revenue_events WHERE event_at >= datetime('now', '-7 days')"
        ).fetchone()[0]

        # Revenue last 30 days
        rev_30d = cur.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM revenue_events WHERE event_at >= datetime('now', '-30 days')"
        ).fetchone()[0]

        # Daily breakdown (last 30 days)
        daily = cur.execute(
            """
            SELECT date(event_at) AS day, SUM(amount_cents) AS cents, COUNT(*) AS orders
            FROM revenue_events
            WHERE event_at >= datetime('now', '-30 days')
            GROUP BY date(event_at)
            ORDER BY day
            """
        ).fetchall()

        return {
            "total_revenue_cents": total_revenue,
            "total_orders": total_orders,
            "total_products": total_products,
            "active_products": active_products,
            "revenue_24h_cents": rev_24h,
            "revenue_7d_cents": rev_7d,
            "revenue_30d_cents": rev_30d,
            "daily": [{"day": r["day"], "cents": r["cents"], "orders": r["orders"]} for r in daily],
        }

    def get_stats(self) -> dict:
        """Get aggregate statistics across all runs."""
        cur = self.conn.cursor()

        total = cur.execute("SELECT COUNT(*) FROM workflow_runs").fetchone()[0]
        completed = cur.execute("SELECT COUNT(*) FROM workflow_runs WHERE status = 'completed'").fetchone()[0]
        failed = cur.execute("SELECT COUNT(*) FROM workflow_runs WHERE status = 'failed'").fetchone()[0]
        running = cur.execute("SELECT COUNT(*) FROM workflow_runs WHERE status = 'running'").fetchone()[0]

        last_run = cur.execute(
            "SELECT started_at, status FROM workflow_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()

        return {
            "total_runs": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "success_rate": round(completed / total * 100, 1) if total > 0 else 0,
            "last_run": dict(last_run) if last_run else None,
        }


# Global singleton
db = VhiveDB()
