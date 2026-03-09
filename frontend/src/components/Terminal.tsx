import { useEffect, useRef } from "react";
import { Terminal as XTerm } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";

interface TerminalProps {
  content: string;
  stderr?: string;
  className?: string;
}

export function Terminal({ content, stderr = "", className = "" }: TerminalProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<XTerm | null>(null);
  const fitRef = useRef<FitAddon | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const xterm = new XTerm({
      theme: {
        background: "#0d0d0d",
        foreground: "#e6b422",
        cursor: "#e6b422",
        black: "#1a1a1a",
        red: "#c94c4c",
        green: "#7cb87c",
        yellow: "#e6b422",
        blue: "#5a8fbd",
        magenta: "#b85cb8",
        cyan: "#5ab8b8",
        white: "#c8c8c8",
      },
      fontFamily: '"JetBrains Mono", "Fira Code", monospace',
      fontSize: 13,
      allowProposedApi: false,
    });

    const fitAddon = new FitAddon();
    xterm.loadAddon(fitAddon);
    xterm.open(containerRef.current);
    fitAddon.fit();

    xtermRef.current = xterm;
    fitRef.current = fitAddon;

    return () => {
      xterm.dispose();
      xtermRef.current = null;
      fitRef.current = null;
    };
  }, []);

  useEffect(() => {
    const xterm = xtermRef.current;
    if (!xterm) return;
    xterm.clear();
    if (content) {
      xterm.writeln(content.replace(/\r?\n/g, "\r\n"));
    }
    if (stderr) {
      xterm.write("\r\n\x1b[31m");
      xterm.writeln(stderr.replace(/\r?\n/g, "\r\n"));
      xterm.write("\x1b[0m");
    }
  }, [content, stderr]);

  return <div ref={containerRef} className={`terminal-container ${className}`} />;
}
