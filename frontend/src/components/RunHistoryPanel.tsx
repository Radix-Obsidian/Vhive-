import { useCallback, useEffect, useState } from "react";
import { getToken } from "../auth";

interface WorkflowRun {
  id: string;
  started_at: string;
  ended_at: string | null;
  status: string;
  trigger_source: string;
  error_message: string | null;
}

interface RunStats {
  total_runs: number;
  completed: number;
  failed: number;
  running: number;
  success_rate: number;
  last_run: { started_at: string; status: string } | null;
}

const API_BASE = import.meta.env.VITE_VHIVE_API_URL || "";

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(start: string, end: string | null): string {
  if (!end) return "running…";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

export function RunHistoryPanel() {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [stats, setStats] = useState<RunStats | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const token = getToken();
      const headers: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : {};
      const [runsRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/api/runs?limit=20`, { headers }),
        fetch(`${API_BASE}/api/stats`, { headers }),
      ]);
      if (runsRes.ok) setRuns(await runsRes.json());
      if (statsRes.ok) setStats(await statsRes.json());
    } catch {
      // Silently fail — will retry on next interval
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const statusDot = (status: string) => {
    switch (status) {
      case "completed":
        return "bg-green-500 shadow-[0_0_6px_#22c55e]";
      case "failed":
        return "bg-red-500 shadow-[0_0_6px_#ef4444]";
      case "running":
        return "bg-amber-400 shadow-[0_0_6px_#f59e0b] animate-pulse";
      default:
        return "bg-gray-500";
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Stats bar */}
      {stats && (
        <div className="flex gap-4 px-4 py-3 border-b border-amber-500/20 bg-amber-500/5 text-xs font-mono">
          <span className="text-amber-400">
            RUNS: <span className="text-[#e8e4dc]">{stats.total_runs}</span>
          </span>
          <span className="text-green-400">
            OK: <span className="text-[#e8e4dc]">{stats.completed}</span>
          </span>
          <span className="text-red-400">
            FAIL: <span className="text-[#e8e4dc]">{stats.failed}</span>
          </span>
          <span className="text-amber-400">
            RATE: <span className="text-[#e8e4dc]">{stats.success_rate}%</span>
          </span>
        </div>
      )}

      {/* Run list */}
      <div className="flex-1 overflow-y-auto p-3">
        {loading && (
          <p className="text-gray-500 text-sm font-mono">Loading run history…</p>
        )}

        {!loading && runs.length === 0 && (
          <p className="text-gray-500 text-sm font-mono">
            No runs yet. Trigger a workflow to see history here.
          </p>
        )}

        <div className="flex flex-col gap-2">
          {runs.map((run) => (
            <div
              key={run.id}
              className="rounded border border-amber-500/20 bg-[#0d0d10]/80 p-3 font-mono text-sm"
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${statusDot(run.status)}`} />
                  <span className="text-amber-400 text-xs uppercase tracking-wider">
                    {run.status}
                  </span>
                </div>
                <span className="text-gray-500 text-xs">
                  {run.trigger_source}
                </span>
              </div>

              <div className="flex items-center justify-between text-xs text-gray-400">
                <span>{formatTime(run.started_at)}</span>
                <span>{formatDuration(run.started_at, run.ended_at)}</span>
              </div>

              {run.error_message && (
                <p className="text-red-400/80 text-xs mt-1 truncate">
                  {run.error_message}
                </p>
              )}

              <span className="text-gray-600 text-[0.6rem] mt-1 block">
                {run.id}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
