import type { CrewAIAgentPayload } from "../types/vhive-ws";

interface ThoughtStreamProps {
  events: CrewAIAgentPayload[];
}

export function ThoughtStream({ events }: ThoughtStreamProps) {
  return (
    <div className="thought-stream flex flex-col gap-2 overflow-y-auto p-3">
      {events.length === 0 && (
        <p className="text-gray-500 text-sm">Agent thoughts will appear here when the workflow runs.</p>
      )}
      {events.map((e, i) => (
        <div
          key={i}
          className="thought-item rounded border border-amber-500/20 bg-[#0d0d10]/80 p-2 font-mono text-sm"
        >
          {e.event === "started" && (
            <span className="text-amber-400">[{e.agent}] started</span>
          )}
          {e.event === "thought" && e.payload?.content && (
            <>
              <span className="text-amber-500/80 block mb-1">
                {e.payload.agent_role ?? e.agent}
                {e.payload.task ? ` · ${e.payload.task}` : ""}
              </span>
              <pre className="text-[#e8e4dc] whitespace-pre-wrap break-words m-0">
                {e.payload.content}
              </pre>
            </>
          )}
          {e.event === "finished" && (
            <span className="text-green-400">[{e.agent}] finished</span>
          )}
        </div>
      ))}
    </div>
  );
}
