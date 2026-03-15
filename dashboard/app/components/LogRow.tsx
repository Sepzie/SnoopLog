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

function accentBorder(score: number): string {
  if (score >= 0.7) return "border-l-rose-400";
  if (score >= 0.3) return "border-l-amber-300";
  return "border-l-emerald-300";
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
  const timestamp = log.timestamp
    ? new Date(log.timestamp).toLocaleTimeString()
    : "unknown";
  const level = (log.level ?? "info").toUpperCase();
  const score = Number(log.pipeline?.anomaly_score ?? 0);

  return (
    <div
      className={`rounded-lg border border-black/4 border-l-[3px] ${accentBorder(score)} bg-white/80 px-3 py-2 transition hover:bg-white`}
    >
      <div className="flex items-center gap-2 text-[11px]">
        <span className="text-[var(--muted)]">{timestamp}</span>
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${levelBadge(level)}`}
        >
          {level}
        </span>
        <span className="min-w-0 flex-1 truncate text-[#4d4a57]">
          {log.message ?? "(no message)"}
        </span>
      </div>
    </div>
  );
}
