"use client";

import { useMemo } from "react";
import { useLiveData } from "./live-data";
import { AgentStatusCard } from "./AgentStatusCard";

type LiveStatsProps = {
  onOpenAgentTrail: () => void;
};

export function LiveStats({ onOpenAgentTrail }: LiveStatsProps) {
  const { logs, incidents } = useLiveData();

  const { recentLogs, recentAnomalies, recentEscalations } = useMemo(() => {
    const cutoff = Date.now() - 86_400_000;
    let logCount = 0;
    let anomalyCount = 0;
    for (const log of logs) {
      if (log.timestamp && new Date(log.timestamp).getTime() > cutoff) {
        logCount++;
        if (log.pipeline?.tier === "high") anomalyCount++;
      }
    }
    const escCount = incidents.filter(
      (inc) => new Date(inc.timestamp).getTime() > cutoff,
    ).length;

    return {
      recentLogs: logCount,
      recentAnomalies: anomalyCount,
      recentEscalations: escCount,
    };
  }, [logs, incidents]);

  const stats = [
    { label: "Logs", value: recentLogs, sub: "recent" },
    { label: "Anomalies", value: recentAnomalies, sub: "recent" },
    { label: "Escalations", value: recentEscalations, sub: "recent" },
  ];

  return (
    <section className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      {stats.map((stat) => (
        <div
          key={stat.label}
          className="rounded-2xl border border-black/8 bg-white px-4 py-4 shadow-[0_8px_30px_rgba(20,20,20,0.04)]"
        >
          <p className="text-sm text-[#666372]">{stat.label}</p>
          <p className="mt-3 text-3xl font-semibold tracking-[-0.03em] text-[#262330]">
            {stat.value.toLocaleString()}
          </p>
          <p className="mt-1 text-[11px] text-[var(--muted)]">{stat.sub}</p>
        </div>
      ))}
      <AgentStatusCard onOpenTrail={onOpenAgentTrail} />
    </section>
  );
}
