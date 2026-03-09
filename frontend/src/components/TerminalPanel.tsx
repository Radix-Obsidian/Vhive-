import { useRef, useEffect, useState } from "react";
import type { DockerTerminalPayload } from "../types/vhive-ws";
import { Terminal } from "./Terminal";

interface TerminalPanelProps {
  history: DockerTerminalPayload[];
}

export function TerminalPanel({ history }: TerminalPanelProps) {
  const [combined, setCombined] = useState({ stdout: "", stderr: "" });
  const prevLen = useRef(0);

  useEffect(() => {
    if (history.length === prevLen.current) return;
    prevLen.current = history.length;
    const out = history
      .map((h) => (h.stdout ? h.stdout + (h.stdout.endsWith("\n") ? "" : "\n") : ""))
      .join("");
    const err = history
      .map((h) => (h.stderr ? h.stderr + (h.stderr.endsWith("\n") ? "" : "\n") : ""))
      .join("");
    setCombined((prev) => ({
      stdout: prev.stdout + out,
      stderr: prev.stderr + err,
    }));
  }, [history]);

  return (
    <div className="terminal-panel h-full flex flex-col rounded overflow-hidden bg-[#0d0d10]">
      <div className="flex-1 min-h-0 p-2">
        <Terminal content={combined.stdout} stderr={combined.stderr} className="h-full w-full" />
      </div>
    </div>
  );
}
