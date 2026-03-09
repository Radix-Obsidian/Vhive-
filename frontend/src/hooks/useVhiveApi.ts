/**
 * Simple fetch wrapper for Vhive API calls.
 * Reads base URL from VITE_VHIVE_API_URL (defaults to same origin).
 * Attaches Bearer token from auth module.
 */

import { getToken } from "../auth";

const API_BASE = import.meta.env.VITE_VHIVE_API_URL || "";

async function apiFetch<T = unknown>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.message || body.error || `API error ${res.status}`);
  }

  return res.json();
}

export function useVhiveApi() {
  return {
    triggerRun: () =>
      apiFetch<{ status: string; message?: string }>("/run", {
        method: "POST",
      }),

    triggerDemo: () =>
      apiFetch<{ status: string }>("/demo", { method: "POST" }),

    fetchRuns: (limit = 20) =>
      apiFetch<
        Array<{
          id: string;
          started_at: string;
          ended_at: string | null;
          status: string;
          trigger_source: string;
          error_message: string | null;
        }>
      >(`/api/runs?limit=${limit}`),

    fetchStats: () =>
      apiFetch<{
        total_runs: number;
        completed: number;
        failed: number;
        running: number;
        success_rate: number;
      }>("/api/stats"),

    fetchSchedule: () =>
      apiFetch<{
        enabled: boolean;
        next_run: string | null;
        interval_hours: number | null;
        last_heartbeat: string | null;
      }>("/api/schedule"),

    updateSchedule: (hours: number) =>
      apiFetch("/api/schedule", {
        method: "POST",
        body: JSON.stringify({ hours }),
      }),

    fetchRevenue: () =>
      apiFetch<{
        total_revenue_cents: number;
        total_orders: number;
        total_products: number;
        active_products: number;
        revenue_24h_cents: number;
        revenue_7d_cents: number;
        revenue_30d_cents: number;
        daily: Array<{ day: string; cents: number; orders: number }>;
      }>("/api/revenue"),

    fetchProducts: (limit = 50) =>
      apiFetch<
        Array<{
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
        }>
      >(`/api/products?limit=${limit}`),

    syncRevenue: () =>
      apiFetch<{
        total_revenue_cents: number;
        total_orders: number;
        total_products: number;
        active_products: number;
        revenue_24h_cents: number;
        revenue_7d_cents: number;
        revenue_30d_cents: number;
        daily: Array<{ day: string; cents: number; orders: number }>;
      }>("/api/revenue/sync", { method: "POST" }),
  };
}
