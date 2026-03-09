import { useCallback, useEffect, useState } from "react";
import { useVhiveApi } from "../hooks/useVhiveApi";

interface RevenueSummary {
  total_revenue_cents: number;
  total_orders: number;
  total_products: number;
  active_products: number;
  revenue_24h_cents: number;
  revenue_7d_cents: number;
  revenue_30d_cents: number;
  daily: Array<{ day: string; cents: number; orders: number }>;
}

interface Product {
  id: string;
  run_id: string;
  shopify_gid: string;
  title: string;
  product_type: string;
  price_cents: number;
  status: string;
  created_at: string;
  total_revenue_cents: number;
  order_count: number;
}

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/* ── Sparkline bar chart (pure CSS) ──────────────────────── */

function MiniChart({ daily }: { daily: RevenueSummary["daily"] }) {
  if (daily.length === 0) {
    return (
      <p className="text-gray-600 text-xs font-mono text-center py-8">
        No revenue data yet
      </p>
    );
  }

  const maxCents = Math.max(...daily.map((d) => d.cents), 1);

  return (
    <div className="flex items-end gap-px h-28 px-1">
      {daily.map((d) => {
        const pct = Math.max((d.cents / maxCents) * 100, 2);
        return (
          <div
            key={d.day}
            className="flex-1 group relative"
            title={`${d.day}: ${formatCents(d.cents)} (${d.orders} orders)`}
          >
            <div
              className="bg-amber-400/70 hover:bg-amber-400 rounded-t-sm transition-colors w-full"
              style={{ height: `${pct}%` }}
            />
            {/* Tooltip on hover */}
            <div className="hidden group-hover:block absolute bottom-full left-1/2 -translate-x-1/2 mb-1 bg-[#1a1a1e] border border-amber-500/30 rounded px-2 py-1 text-[0.6rem] font-mono text-amber-300 whitespace-nowrap z-10">
              {d.day}: {formatCents(d.cents)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ── Main dashboard ──────────────────────────────────────── */

export function RevenueDashboard() {
  const api = useVhiveApi();
  const [revenue, setRevenue] = useState<RevenueSummary | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [rev, prods] = await Promise.all([
        api.fetchRevenue(),
        api.fetchProducts(),
      ]);
      setRevenue(rev);
      setProducts(prods);
    } catch {
      // Will retry on next interval
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleSync = useCallback(async () => {
    setSyncing(true);
    try {
      const rev = await api.syncRevenue();
      setRevenue(rev);
      // Refresh products too
      const prods = await api.fetchProducts();
      setProducts(prods);
    } catch {
      // Sync might fail if Shopify creds aren't set
    } finally {
      setSyncing(false);
    }
  }, []);

  if (loading) {
    return (
      <p className="text-gray-500 text-sm font-mono p-4">
        Loading revenue data...
      </p>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 p-4">
        <KPICard
          label="Total Revenue"
          value={formatCents(revenue?.total_revenue_cents ?? 0)}
          accent="text-green-400"
        />
        <KPICard
          label="Orders"
          value={String(revenue?.total_orders ?? 0)}
          accent="text-amber-400"
        />
        <KPICard
          label="Products"
          value={`${revenue?.active_products ?? 0} active`}
          sub={`${revenue?.total_products ?? 0} total`}
          accent="text-blue-400"
        />
        <KPICard
          label="Last 24h"
          value={formatCents(revenue?.revenue_24h_cents ?? 0)}
          sub={`7d: ${formatCents(revenue?.revenue_7d_cents ?? 0)}`}
          accent="text-purple-400"
        />
      </div>

      {/* Chart + sync button */}
      <div className="px-4 pb-2 flex items-center justify-between">
        <span className="text-amber-400/80 text-xs font-mono tracking-widest uppercase">
          Daily Revenue (30d)
        </span>
        <button
          onClick={handleSync}
          disabled={syncing}
          className={`text-[0.65rem] font-mono uppercase tracking-wider px-2 py-1 rounded border ${
            syncing
              ? "border-amber-500/20 text-amber-500/30 cursor-not-allowed"
              : "border-amber-500/40 text-amber-400/70 hover:bg-amber-500/10 cursor-pointer"
          }`}
        >
          {syncing ? "Syncing..." : "Sync Now"}
        </button>
      </div>
      <div className="px-4 pb-4">
        <div className="border border-amber-500/20 rounded-lg bg-[#0a0a0c] p-3">
          <MiniChart daily={revenue?.daily ?? []} />
        </div>
      </div>

      {/* Product table */}
      <div className="px-4 pb-4 flex-1">
        <span className="text-amber-400/80 text-xs font-mono tracking-widest uppercase block mb-2">
          Deployed Products
        </span>

        {products.length === 0 ? (
          <p className="text-gray-600 text-xs font-mono">
            No products deployed yet. Run a workflow to create your first product.
          </p>
        ) : (
          <div className="border border-amber-500/20 rounded-lg overflow-hidden">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-amber-500/20 bg-amber-500/5 text-amber-400/80">
                  <th className="text-left px-3 py-2 font-normal tracking-wider">
                    Product
                  </th>
                  <th className="text-right px-3 py-2 font-normal tracking-wider">
                    Revenue
                  </th>
                  <th className="text-right px-3 py-2 font-normal tracking-wider">
                    Orders
                  </th>
                  <th className="text-right px-3 py-2 font-normal tracking-wider">
                    Status
                  </th>
                  <th className="text-right px-3 py-2 font-normal tracking-wider">
                    Created
                  </th>
                </tr>
              </thead>
              <tbody>
                {products.map((p) => (
                  <tr
                    key={p.id}
                    className="border-b border-amber-500/10 hover:bg-amber-500/5"
                  >
                    <td className="px-3 py-2 text-[#e8e4dc]">
                      <div className="truncate max-w-[200px]">{p.title}</div>
                      <div className="text-gray-600 text-[0.6rem]">
                        {p.product_type}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right text-green-400">
                      {formatCents(p.total_revenue_cents)}
                    </td>
                    <td className="px-3 py-2 text-right text-[#e8e4dc]">
                      {p.order_count}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span
                        className={
                          p.status === "active"
                            ? "text-green-400"
                            : "text-gray-500"
                        }
                      >
                        {p.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right text-gray-400">
                      {formatDateTime(p.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── KPI Card ────────────────────────────────────────────── */

function KPICard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent: string;
}) {
  return (
    <div className="border border-amber-500/20 rounded-lg bg-[#0a0a0c] p-3">
      <div className="text-[0.6rem] font-mono uppercase tracking-widest text-gray-500 mb-1">
        {label}
      </div>
      <div className={`text-lg font-bold font-mono ${accent}`}>{value}</div>
      {sub && (
        <div className="text-[0.6rem] font-mono text-gray-500 mt-0.5">
          {sub}
        </div>
      )}
    </div>
  );
}
