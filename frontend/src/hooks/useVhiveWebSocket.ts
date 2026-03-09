import { useCallback, useEffect, useRef, useState } from "react";
import type { VhiveWSMessage } from "../types/vhive-ws";
import { parseVhiveMessage } from "../types/vhive-ws";
import { getToken } from "../auth";

function getDefaultWsUrl(): string {
  // Env var override (build-time)
  if (
    typeof import.meta.env.VITE_VHIVE_WS_URL === "string" &&
    import.meta.env.VITE_VHIVE_WS_URL
  ) {
    return import.meta.env.VITE_VHIVE_WS_URL;
  }
  // Auto-detect from current page URL (works for same-origin deploys & Tailscale)
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

const DEFAULT_WS_URL = getDefaultWsUrl();

export type ConnectionStatus = "connecting" | "connected" | "disconnected" | "error";

export interface UseVhiveWebSocketOptions {
  url?: string;
  onMessage?: (msg: VhiveWSMessage) => void;
  reconnect?: boolean;
  reconnectIntervalMs?: number;
}

export function useVhiveWebSocket(options: UseVhiveWebSocketOptions = {}) {
  const {
    url = DEFAULT_WS_URL,
    onMessage,
    reconnect = true,
    reconnectIntervalMs = 3000,
  } = options;

  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [lastMessage, setLastMessage] = useState<VhiveWSMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus("connecting");
    const token = getToken();
    const wsUrl = token ? `${url}?token=${encodeURIComponent(token)}` : url;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => setStatus("connected");

    ws.onmessage = (event: MessageEvent) => {
      const msg = parseVhiveMessage(
        typeof event.data === "string" ? event.data : ""
      );
      if (msg) {
        setLastMessage(msg);
        onMessageRef.current?.(msg);
      }
    };

    ws.onclose = () => {
      wsRef.current = null;
      setStatus("disconnected");
      if (reconnect) {
        reconnectTimeoutRef.current = setTimeout(
          () => connect(),
          reconnectIntervalMs
        );
      }
    };

    ws.onerror = () => setStatus("error");
    wsRef.current = ws;
  }, [url, reconnect, reconnectIntervalMs]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus("disconnected");
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  return { status, lastMessage, connect, disconnect };
}
