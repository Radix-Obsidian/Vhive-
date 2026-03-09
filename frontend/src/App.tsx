import { useCallback, useEffect, useMemo, useState } from "react";
import { useVhiveWebSocket } from "./hooks/useVhiveWebSocket";
import { useVhiveApi } from "./hooks/useVhiveApi";
import { hasToken, setToken, clearToken } from "./auth";
import type {
  VhiveWSMessage,
  WorkflowPayload,
  LangGraphStatePayload,
  CrewAIAgentPayload,
  DockerTerminalPayload,
} from "./types/vhive-ws";
import { ThoughtStream } from "./components/ThoughtStream";
import { TerminalPanel } from "./components/TerminalPanel";
import { WorkflowStatePanel } from "./components/WorkflowStatePanel";
import { RunHistoryPanel } from "./components/RunHistoryPanel";
import { RevenueDashboard } from "./components/RevenueDashboard";

type WorkflowEvent = "idle" | "started" | "completed" | "error";
type ActiveTab = "mission-control" | "history" | "revenue";

/* ── Auth Gate ──────────────────────────────────────────────── */

function AuthGate({ onAuth }: { onAuth: () => void }) {
  const [key, setKey] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = key.trim();
    if (!trimmed) return;

    // Test the key against /health first? No — /health is public.
    // Instead, try a protected endpoint.
    setToken(trimmed);
    try {
      const res = await fetch(
        `${import.meta.env.VITE_VHIVE_API_URL || ""}/api/stats`,
        { headers: { Authorization: `Bearer ${trimmed}` } }
      );
      if (res.status === 401) {
        clearToken();
        setError("Invalid API key");
        return;
      }
      onAuth();
    } catch {
      clearToken();
      setError("Cannot reach Vhive server");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0a0c]">
      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-4 border border-amber-500/30 rounded-lg p-8 bg-[#0d0d10] max-w-md w-full"
      >
        <h1 className="text-xl font-bold tracking-[0.35em] text-amber-400 text-center">
          STAR OFFICE
        </h1>
        <p className="text-xs text-amber-500/60 text-center font-mono uppercase tracking-wider">
          Enter your API key to continue
        </p>
        <input
          type="password"
          value={key}
          onChange={(e) => {
            setKey(e.target.value);
            setError("");
          }}
          placeholder="Paste API key from server startup"
          className="bg-[#0a0a0c] border border-amber-500/30 rounded px-3 py-2 text-sm font-mono text-[#e8e4dc] placeholder:text-gray-600 focus:outline-none focus:border-amber-400"
          autoFocus
        />
        {error && (
          <p className="text-xs text-red-400 font-mono text-center">{error}</p>
        )}
        <button
          type="submit"
          className="border border-amber-500/50 text-amber-400 hover:bg-amber-500/10 text-xs font-mono uppercase tracking-wider px-3 py-2 rounded cursor-pointer"
        >
          Authenticate
        </button>
        <p className="text-[0.6rem] text-gray-600 text-center font-mono">
          Key is printed on server start: python -m vhive_core.main --server
        </p>
      </form>
    </div>
  );
}

/* ── Main App ──────────────────────────────────────────────── */

function App() {
  const [authed, setAuthed] = useState(hasToken);

  if (!authed) {
    return <AuthGate onAuth={() => setAuthed(true)} />;
  }
  const api = useVhiveApi();
  const [activeTab, setActiveTab] = useState<ActiveTab>("mission-control");
  const [workflowEvent, setWorkflowEvent] = useState<WorkflowEvent>("idle");
  const [workflowError, setWorkflowError] = useState<string | undefined>();
  const [langGraphState, setLangGraphState] = useState<LangGraphStatePayload | null>(null);
  const [agentEvents, setAgentEvents] = useState<CrewAIAgentPayload[]>([]);
  const [terminalHistory, setTerminalHistory] = useState<DockerTerminalPayload[]>([]);
  const [nextRun, setNextRun] = useState<string | null>(null);
  const [isTriggering, setIsTriggering] = useState(false);

  const handleMessage = useCallback((msg: VhiveWSMessage) => {
    switch (msg.type) {
      case "workflow": {
        const p = msg.payload as WorkflowPayload;
        setWorkflowEvent(p.event === "started" ? "started" : p.event === "completed" ? "completed" : p.event === "error" ? "error" : "idle");
        if (p.event === "error" && p.message) setWorkflowError(p.message);
        if (p.event === "completed" || p.event === "error") setIsTriggering(false);
        break;
      }
      case "langgraph_state":
        setLangGraphState(msg.payload as LangGraphStatePayload);
        break;
      case "crewai_agent":
        setAgentEvents((prev) => [...prev, msg.payload as CrewAIAgentPayload]);
        break;
      case "docker_terminal":
        setTerminalHistory((prev) => [...prev, msg.payload as DockerTerminalPayload]);
        break;
    }
  }, []);

  const { status } = useVhiveWebSocket({ onMessage: handleMessage });

  // Fetch schedule info
  useEffect(() => {
    const fetchSchedule = async () => {
      try {
        const info = await api.fetchSchedule();
        setNextRun(info.next_run);
      } catch {
        // Scheduler might not be running
      }
    };
    fetchSchedule();
    const interval = setInterval(fetchSchedule, 60_000);
    return () => clearInterval(interval);
  }, []);

  const handleRunNow = useCallback(async () => {
    setIsTriggering(true);
    setWorkflowEvent("idle");
    setWorkflowError(undefined);
    setAgentEvents([]);
    setTerminalHistory([]);
    setActiveTab("mission-control");
    try {
      await api.triggerRun();
    } catch (e) {
      setIsTriggering(false);
      setWorkflowError(e instanceof Error ? e.message : "Failed to trigger");
    }
  }, [api]);

  const handleDemo = useCallback(async () => {
    setIsTriggering(true);
    setWorkflowEvent("idle");
    setAgentEvents([]);
    setTerminalHistory([]);
    setActiveTab("mission-control");
    try {
      await api.triggerDemo();
    } catch {
      setIsTriggering(false);
    }
  }, [api]);

  const isRunning = workflowEvent === "started" || isTriggering;

  const statusLabel = useMemo(() => {
    switch (status) {
      case "connecting": return "Connecting\u2026";
      case "connected": return "Connected";
      case "disconnected": return "Disconnected";
      case "error": return "Error";
      default: return "\u2014";
    }
  }, [status]);

  const formatNextRun = (iso: string | null) => {
    if (!iso) return null;
    const d = new Date(iso);
    const now = Date.now();
    const diffMs = d.getTime() - now;
    if (diffMs < 0) return "soon";
    const h = Math.floor(diffMs / 3600000);
    const m = Math.floor((diffMs % 3600000) / 60000);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
  };

  const tabClass = (tab: ActiveTab) =>
    `text-xs font-mono uppercase tracking-wider px-3 py-1.5 rounded cursor-pointer border ${
      activeTab === tab
        ? "border-amber-400 text-amber-400 bg-amber-500/15"
        : "border-amber-500/30 text-amber-500/60 hover:bg-amber-500/10"
    }`;

  return (
    <div className="star-office-app min-h-screen flex flex-col bg-[#0a0a0c] text-[#e8e4dc]">
      <header className="star-header border-b border-amber-500/30 flex items-center justify-between px-5 py-3 bg-[#060608]">
        <div className="flex flex-col">
          <h1 className="text-xl font-bold tracking-[0.35em] text-amber-400">
            ★ STAR OFFICE
          </h1>
          <span className="text-[0.65rem] tracking-[0.2em] text-amber-500/80 uppercase mt-0.5">
            AURA Mission Control · Vhive
          </span>
        </div>
        <div className="flex items-center gap-3">
          {/* Workflow controls */}
          <button
            onClick={handleRunNow}
            disabled={isRunning}
            className={`text-xs font-mono uppercase tracking-wider px-3 py-1.5 rounded border ${
              isRunning
                ? "border-amber-500/20 text-amber-500/30 cursor-not-allowed"
                : "border-green-500/60 text-green-400 hover:bg-green-500/10 cursor-pointer"
            }`}
          >
            {isRunning ? "Running\u2026" : "\u25B6 Run Now"}
          </button>
          <button
            onClick={handleDemo}
            disabled={isRunning}
            className={`text-xs font-mono uppercase tracking-wider px-3 py-1.5 rounded border ${
              isRunning
                ? "border-amber-500/20 text-amber-500/30 cursor-not-allowed"
                : "border-amber-500/50 text-amber-400 hover:bg-amber-500/10 cursor-pointer"
            }`}
          >
            Demo
          </button>

          {/* Next scheduled run */}
          {nextRun && (
            <span className="text-[0.6rem] font-mono text-gray-500 uppercase tracking-wider">
              Next: {formatNextRun(nextRun)}
            </span>
          )}

          {/* Divider */}
          <span className="w-px h-5 bg-amber-500/20" />

          {/* Tab switcher */}
          <div className="flex items-center gap-2">
            <button className={tabClass("mission-control")} onClick={() => setActiveTab("mission-control")}>
              Live
            </button>
            <button className={tabClass("history")} onClick={() => setActiveTab("history")}>
              History
            </button>
            <button className={tabClass("revenue")} onClick={() => setActiveTab("revenue")}>
              Revenue
            </button>
          </div>

          {/* WS status */}
          <div className="flex items-center gap-2">
            {status === "connected" ? (
              <span className="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_#7cb87c]" title="Live" />
            ) : (
              <span className="w-2 h-2 rounded-full bg-gray-600" title="Offline" />
            )}
            <span className={`text-xs font-mono uppercase tracking-wider ${status === "connected" ? "text-green-400" : "text-gray-500"}`}>
              WS: {statusLabel}
            </span>
          </div>
          <a
            href="/docs"
            target="_blank"
            rel="noreferrer"
            className="text-xs font-mono uppercase tracking-wider border border-amber-500/50 px-3 py-1.5 rounded text-amber-400 hover:bg-amber-500/10"
          >
            API
          </a>
          <button
            onClick={() => { clearToken(); setAuthed(false); }}
            className="text-xs font-mono uppercase tracking-wider border border-red-500/40 px-3 py-1.5 rounded text-red-400/70 hover:bg-red-500/10 cursor-pointer"
            title="Sign out"
          >
            Logout
          </button>
        </div>
      </header>

      {activeTab === "mission-control" && (
        <main className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-4 p-4 min-h-0 bg-[#0a0a0c]">
          <section className="lg:col-span-1 flex flex-col min-h-0 border border-amber-500/25 rounded-lg overflow-hidden bg-[#0d0d10]">
            <div className="px-4 py-2.5 border-b border-amber-500/20 bg-amber-500/5">
              <span className="text-amber-400/90 text-sm font-mono tracking-widest">◉ AGENT COMM</span>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              <ThoughtStream events={agentEvents} />
            </div>
          </section>

          <section className="lg:col-span-2 flex flex-col min-h-0 gap-4">
            <div className="flex-shrink-0 border border-amber-500/25 rounded-lg overflow-hidden bg-[#0d0d10]">
              <WorkflowStatePanel
                current={langGraphState}
                workflowEvent={workflowEvent}
                workflowError={workflowError}
              />
            </div>
            <div className="flex-1 min-h-0 flex flex-col border border-amber-500/25 rounded-lg overflow-hidden bg-[#0d0d10]">
              <div className="px-4 py-2.5 border-b border-amber-500/20 bg-amber-500/5">
                <span className="text-amber-400/90 text-sm font-mono tracking-widest">◼ EXECUTION LOG</span>
              </div>
              <div className="flex-1 min-h-0">
                <TerminalPanel history={terminalHistory} />
              </div>
            </div>
          </section>
        </main>
      )}

      {activeTab === "history" && (
        <main className="flex-1 flex flex-col min-h-0 p-4 bg-[#0a0a0c]">
          <div className="flex-1 border border-amber-500/25 rounded-lg overflow-hidden bg-[#0d0d10]">
            <div className="px-4 py-2.5 border-b border-amber-500/20 bg-amber-500/5">
              <span className="text-amber-400/90 text-sm font-mono tracking-widest">◷ RUN HISTORY</span>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              <RunHistoryPanel />
            </div>
          </div>
        </main>
      )}

      {activeTab === "revenue" && (
        <main className="flex-1 flex flex-col min-h-0 p-4 bg-[#0a0a0c]">
          <div className="flex-1 border border-amber-500/25 rounded-lg overflow-hidden bg-[#0d0d10]">
            <div className="px-4 py-2.5 border-b border-amber-500/20 bg-amber-500/5">
              <span className="text-amber-400/90 text-sm font-mono tracking-widest">◈ REVENUE</span>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              <RevenueDashboard />
            </div>
          </div>
        </main>
      )}
    </div>
  );
}

export default App;
