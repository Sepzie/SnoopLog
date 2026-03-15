"use client";

import { useState } from "react";

export type PipelineState = {
  anomaly_score?: number;
  tier?: string;
};

export type LogEvent = {
  id?: string;
  timestamp?: string;
  level?: string;
  message?: string;
  pipeline?: PipelineState;
};

type LogRowProps = {
  log: LogEvent;
};

function scoreColor(score: number): {
  border: string;
  bar: string;
  barBg: string;
} {
  if (score >= 0.7)
    return {
      border: "border-l-rose-400",
      bar: "bg-rose-400",
      barBg: "bg-rose-100",
    };
  if (score >= 0.3)
    return {
      border: "border-l-amber-300",
      bar: "bg-amber-400",
      barBg: "bg-amber-100",
    };
  return {
    border: "border-l-emerald-300",
    bar: "bg-emerald-400",
    barBg: "bg-emerald-100",
  };
}

function levelBadge(level: string): string {
  if (level === "ERROR" || level === "FATAL") {
    return "border border-rose-300/60 bg-rose-100 text-rose-700";
  }
  if (level === "WARN") {
    return "border border-amber-300/70 bg-amber-100 text-amber-800";
  }
  return "border border-emerald-300/70 bg-emerald-100 text-emerald-700";
}

export function LogRow({ log }: LogRowProps) {
  const [expanded, setExpanded] = useState(false);
  const timestamp = log.timestamp
    ? new Date(log.timestamp).toLocaleTimeString()
    : "unknown";
  const level = (log.level ?? "info").toUpperCase();
  const score = Number(log.pipeline?.anomaly_score ?? 0);
  const colors = scoreColor(score);
  const pct = Math.max(Math.round(score * 100), 1);

  return (
    <div
      className={`overflow-hidden rounded-lg border border-black/4 border-l-[3px] ${colors.border} bg-white/80 transition hover:bg-white cursor-pointer`}
      onClick={() => setExpanded((v) => !v)}
    >
      <div className="flex items-center gap-2 px-3 py-2 text-[11px]">
        <span className="text-[var(--muted)]">{timestamp}</span>
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${levelBadge(level)}`}
        >
          {level}
        </span>
        <span
          className={`min-w-0 flex-1 text-[#4d4a57] ${expanded ? "whitespace-pre-wrap break-words" : "truncate"}`}
        >
          {log.message ?? "(no message)"}
        </span>
      </div>
      {/* Anomaly score ribbon */}
      <div className={`h-[3px] w-full ${colors.barBg}`}>
        <div
          className={`h-full ${colors.bar} transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
