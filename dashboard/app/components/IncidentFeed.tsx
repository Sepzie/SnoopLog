"use client";

import { useMemo } from "react";
import { IncidentCard } from "./IncidentCard";
import { useLiveData } from "./live-data";

type IncidentFeedProps = {
  onSelectIncident: (id: string) => void;
};

export function IncidentFeed({ onSelectIncident }: IncidentFeedProps) {
  const { incidents } = useLiveData();

  const incidentCards = useMemo(() => {
    return incidents.map((incident) => (
      <IncidentCard
        key={incident.id}
        incident={incident}
        onSelect={onSelectIncident}
      />
    ));
  }, [incidents, onSelectIncident]);

  if (incidents.length === 0) {
    return (
      <div className="flex h-full items-center justify-center rounded-2xl border border-dashed border-black/8 bg-white/60 p-6">
        <p className="text-sm text-[var(--muted)]">
          No escalations yet. Incidents will appear here when the agent
          identifies issues.
        </p>
      </div>
    );
  }

  return (
    <div className="agent-scroll h-full min-w-0 space-y-2 overflow-y-auto overflow-x-hidden pr-1">
      {incidentCards}
    </div>
  );
}
