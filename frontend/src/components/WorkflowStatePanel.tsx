import type { LangGraphStatePayload } from "../types/vhive-ws";

interface WorkflowStatePanelProps {
  current: LangGraphStatePayload | null;
  workflowEvent: "idle" | "started" | "completed" | "error";
  workflowError?: string;
}

export function WorkflowStatePanel({
  current,
  workflowEvent,
  workflowError,
}: WorkflowStatePanelProps) {
  return (
    <div className="workflow-panel rounded overflow-hidden bg-[#0d0d10] border border-amber-500/25">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-amber-500/20 bg-amber-500/5">
        <span className="text-amber-400/90 text-sm font-mono tracking-widest">WORKFLOW STATUS</span>
        <span
          className={`text-xs font-mono uppercase ${
            workflowEvent === "started"
              ? "text-amber-400"
              : workflowEvent === "completed"
                ? "text-green-400"
                : workflowEvent === "error"
                  ? "text-red-400"
                  : "text-gray-500"
          }`}
        >
          {workflowEvent === "idle" && "idle"}
          {workflowEvent === "started" && "running"}
          {workflowEvent === "completed" && "completed"}
          {workflowEvent === "error" && "error"}
        </span>
      </div>
      <div className="p-3 text-sm font-mono">
        {workflowError && (
          <p className="text-red-400 mb-2">{workflowError}</p>
        )}
        {current ? (
          <div>
            <p className="text-amber-400/90 mb-1">Node: {current.node}</p>
            <pre className="text-gray-500 text-xs whitespace-pre-wrap break-all overflow-x-auto">
              {JSON.stringify(current.state, null, 2)}
            </pre>
          </div>
        ) : (
          <p className="text-gray-500">No state yet.</p>
        )}
      </div>
    </div>
  );
}
