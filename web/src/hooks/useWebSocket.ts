import { useCallback, useEffect, useRef, useState } from "react";
import type { BusEvent } from "../lib/types";

export type WsStatus = "connecting" | "connected" | "disconnected";

interface Options {
  /** Called for every decoded event object. Should be stable (useCallback). */
  onEvent: (event: BusEvent) => void;
  /** Max buffered events kept in the returned log. Default 200. */
  maxLog?: number;
}

interface WsResult {
  status: WsStatus;
  /** Rolling log of received events, newest first. */
  log: BusEvent[];
  clear: () => void;
}

/**
 * Connects to /ws/events with automatic, jittered exponential backoff.
 *
 * Coded defensively: if the endpoint is missing or drops, status flips to
 * "disconnected" and the rest of the app keeps working (REST polling carries
 * on). Never throws into render.
 */
export function useWebSocket({ onEvent, maxLog = 200 }: Options): WsResult {
  const [status, setStatus] = useState<WsStatus>("connecting");
  const [log, setLog] = useState<BusEvent[]>([]);

  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedByUs = useRef(false);

  const clear = useCallback(() => setLog([]), []);

  useEffect(() => {
    closedByUs.current = false;

    const url = (() => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      return `${proto}://${location.host}/ws/events`;
    })();

    const connect = () => {
      setStatus((s) => (s === "connected" ? s : "connecting"));
      let ws: WebSocket;
      try {
        ws = new WebSocket(url);
      } catch {
        scheduleRetry();
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        retryRef.current = 0;
        setStatus("connected");
      };

      ws.onmessage = (ev) => {
        let parsed: BusEvent | null = null;
        try {
          const obj = JSON.parse(ev.data as string);
          if (obj && typeof obj.type === "string") {
            parsed = {
              type: obj.type,
              data: obj.data ?? {},
              ts: typeof obj.ts === "number" ? obj.ts : Date.now() / 1000,
            };
          }
        } catch {
          /* ignore malformed frames */
        }
        if (!parsed) return;
        const event = parsed;
        setLog((prev) => [event, ...prev].slice(0, maxLog));
        try {
          onEventRef.current(event);
        } catch {
          /* a faulty handler must never kill the socket */
        }
      };

      ws.onerror = () => {
        // onclose will follow; let it handle reconnection.
        try {
          ws.close();
        } catch {
          /* noop */
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        if (closedByUs.current) return;
        setStatus("disconnected");
        scheduleRetry();
      };
    };

    const scheduleRetry = () => {
      if (closedByUs.current) return;
      const attempt = retryRef.current++;
      // 0.5s → 1 → 2 → 4 → 8 (cap), plus up to 400ms jitter.
      const base = Math.min(8000, 500 * 2 ** Math.min(attempt, 4));
      const delay = base + Math.random() * 400;
      timerRef.current = setTimeout(connect, delay);
    };

    connect();

    return () => {
      closedByUs.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      const ws = wsRef.current;
      wsRef.current = null;
      if (ws) {
        ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null;
        try {
          ws.close();
        } catch {
          /* noop */
        }
      }
    };
  }, [maxLog]);

  return { status, log, clear };
}
