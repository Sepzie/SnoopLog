"use client";

import { useEffect, useMemo, useState } from "react";

type PipelineState = {
  anomaly_score?: number;
  tier?: string;
};

type LogEvent = {
  id?: string;
  timestamp?: string;
  level?: string;
  message?: string;
  pipeline?: PipelineState;
};

type BusMessage = {
  type?: string;
  data?: [LogEvent];
};

function scoreBarColor(score: number): string {
  if (score >= 0.7) {
    return "bg-red-500";
  }
  if (score >= 0.3) {
    return "bg-amber-500";
  }
  return "bg-emerald-500";
}

function levelBadge(level: string): string {
  if (level === "ERROR" || level === "FATAL") {
    return "bg-red-100 text-red-700";
  }
  if (level === "WARN") {
    return "bg-amber-100 text-amber-800";
  }
  return "bg-emerald-100 text-emerald-700";
}

export function LogStream() {
  const [logs, setLogs] = useState<LogEvent[]>([]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    const connect = () => {
      const wsUrl = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:3001/ws";
      ws = new WebSocket(wsUrl);

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as BusMessage;
          if (msg.type !== "log:scored" || !msg.data) {
            return;
          }
          setLogs(msg.data.slice(0, 200));
        } catch {
          // Ignore malformed events so the stream stays alive.
        }
      };

      ws.onclose = () => {
        if (stopped) {
          return;
        }
        retryTimer = setTimeout(connect, 1500);
      };
    };

    connect();

    return () => {
      stopped = true;
      if (retryTimer) {
        clearTimeout(retryTimer);
      }
      if (ws && ws.readyState < WebSocket.CLOSING) {
        ws.close();
      }
    };
  }, []);

  const renderedRows = useMemo(() => {
    return logs.map((log) => {
      const timestamp = log.timestamp
        ? new Date(log.timestamp).toLocaleTimeString()
        : "unknown";
      const level = (log.level ?? "info").toUpperCase();
      const tier = (log.pipeline?.tier ?? "low").toUpperCase();
      const score = Number(log.pipeline?.anomaly_score ?? 0);
      const width = `${Math.round(Math.max(0, Math.min(1, score)) * 100)}%`;

      return (
        <div
          key={log.id ?? `${timestamp}-${log.timestamp}`}
          className="rounded border border-slate-200 bg-slate-50 p-2"
        >
          <div className="mb-1 flex items-center gap-2 text-[11px] text-slate-500">
            <span>{timestamp}</span>
            <span
              className={`rounded px-1.5 py-0.5 font-semibold ${levelBadge(level)}`}
            >
              {level}
            </span>
            <span className="rounded bg-slate-200 px-1.5 py-0.5 text-slate-700">
              {tier}
            </span>
          </div>
          <p className="truncate text-slate-700">
            {log.message ?? "(no message)"}
          </p>
          <div className="mt-2 h-1.5 rounded bg-slate-200">
            <div
              className={`h-1.5 rounded ${scoreBarColor(score)}`}
              style={{ width }}
            />
          </div>
        </div>
      );
    });
  }, [logs]);

  if (logs.length === 0) {
    setLogs([
      {
        id: "ID",
        timestamp: "June 2019",
        level: "WARN",
        message: "You have a broken endpoint",
        pipeline: { anomaly_score: 0.7, tier: "low" },
      } as LogEvent,
      {
        id: "I222D",
        timestamp: "June 2019",
        level: "FATAL",
        message: "You have a broken function",
        pipeline: { anomaly_score: 0.2, tier: "low" },
      } as LogEvent,
    ]);
    return (
      <div className="rounded border border-dashed border-slate-300 bg-slate-50 p-4 text-xs text-slate-500">
        Waiting for `log:scored` events...
      </div>
    );
  }

  return <div className="space-y-2 font-mono text-xs">{renderedRows}</div>;
}
