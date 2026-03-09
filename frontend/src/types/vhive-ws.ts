/** Vhive WebSocket message from FastAPI /ws */
export type VhiveWSMessage =
  | { type: "workflow"; payload: WorkflowPayload }
  | { type: "langgraph_state"; payload: LangGraphStatePayload }
  | { type: "crewai_agent"; payload: CrewAIAgentPayload }
  | { type: "docker_terminal"; payload: DockerTerminalPayload };

export interface WorkflowPayload {
  event: "started" | "completed" | "error";
  message?: string;
  final_state?: Record<string, unknown>;
}

export interface LangGraphStatePayload {
  node: string;
  state: Record<string, unknown>;
}

export interface CrewAIAgentPayload {
  event: "started" | "thought" | "finished";
  agent: string;
  payload?: {
    task?: string;
    agent_role?: string;
    content?: string;
    chunk_type?: string;
    result_preview?: string;
  };
}

export interface DockerTerminalPayload {
  stdout: string;
  stderr: string;
  exit_code: number;
  container_id?: string;
}

export function parseVhiveMessage(data: string): VhiveWSMessage | null {
  try {
    const parsed = JSON.parse(data) as { type?: string; payload?: unknown };
    if (typeof parsed.type === "string" && parsed.payload !== undefined) {
      return parsed as VhiveWSMessage;
    }
  } catch {
    // ignore
  }
  return null;
}
