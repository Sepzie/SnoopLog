"use client";

import { useMemo } from "react";
import { LogRow } from "./LogRow";
import { useLiveData } from "./live-data";

export function LogStream() {
  const { logs } = useLiveData();

  const renderedRows = useMemo(() => {
    const reversed = [...logs].reverse();
    return reversed.map((log) => {
      const fallbackKey = `${log.timestamp ?? "unknown"}-${log.message ?? "unknown"}`;
      return <LogRow key={log.id ?? fallbackKey} log={log} />;
    });
  }, [logs]);

  if (logs.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-amber-200 bg-white/60 p-4 text-xs text-slate-500">
        Nothing to report...
      </div>
    );
  }

  return (
    <div className="agent-scroll h-full overflow-y-auto pr-1 font-mono text-xs">
      <div className="space-y-2">{renderedRows}</div>
    </div>
  );
}
