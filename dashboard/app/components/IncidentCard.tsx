"use client";

import type { IncidentFeedItem } from "./incidentTypes";

type IncidentCardProps = {
  incident: IncidentFeedItem;
  onSelect: (id: string) => void;
};

function severityColor(severity: string): {
  border: string;
  badge: string;
  badgeText: string;
} {
  const level = severity.toLowerCase();
  if (level === "critical") {
    return {
      border: "border-l-rose-500",
      badge: "bg-rose-100 border-rose-200",
      badgeText: "text-rose-700",
    };
  }
  if (level === "high") {
    return {
      border: "border-l-rose-400",
      badge: "bg-rose-50 border-rose-200",
      badgeText: "text-rose-700",
    };
  }
  if (level === "medium") {
    return {
      border: "border-l-amber-400",
      badge: "bg-amber-50 border-amber-200",
      badgeText: "text-amber-800",
    };
  }
  return {
    border: "border-l-emerald-400",
    badge: "bg-emerald-50 border-emerald-200",
    badgeText: "text-emerald-700",
  };
}

export function IncidentCard({ incident, onSelect }: IncidentCardProps) {
  const timestamp = new Date(incident.timestamp).toLocaleTimeString();
  const occurrenceCount =
    incident.occurrenceCount ??
    incident.logCount ??
    incident.relatedLogIds.length ??
    1;
  const colors = severityColor(incident.severity);

  return (
    <button
      type="button"
      onClick={() => onSelect(incident.id)}
      className={`group w-full rounded-xl border border-black/6 border-l-4 ${colors.border} bg-white p-3.5 text-left transition-all hover:border-black/10 hover:shadow-[0_4px_16px_rgba(20,20,20,0.06)] active:scale-[0.995]`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex items-center gap-2">
            <span
              className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] ${colors.badge} ${colors.badgeText}`}
            >
              {incident.severity}
            </span>
            <span className="text-[11px] text-[var(--muted)]">
              {timestamp}
            </span>
          </div>
          <p className="truncate text-sm font-medium text-[#2b2735]">
            {incident.summary}
          </p>
          <p className="mt-1 text-[11px] text-[var(--muted)]">
            {incident.source ?? "unknown"} &middot; {occurrenceCount}{" "}
            occurrence{occurrenceCount !== 1 ? "s" : ""}
          </p>
        </div>
        <svg
          className="mt-1 h-4 w-4 shrink-0 text-[#c4c2cc] transition-transform group-hover:translate-x-0.5 group-hover:text-[var(--accent)]"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M9 6L15 12L9 18"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    </button>
  );
}
