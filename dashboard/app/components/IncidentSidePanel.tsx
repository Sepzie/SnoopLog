"use client";

import { useLiveData } from "./live-data";
import { IncidentDetail } from "./IncidentDetail";
import { SidePanel } from "./SidePanel";

type IncidentSidePanelProps = {
  incidentId: string | null;
  onClose: () => void;
};

export function IncidentSidePanel({
  incidentId,
  onClose,
}: IncidentSidePanelProps) {
  const { incidents } = useLiveData();
  const incident = incidentId
    ? incidents.find((inc) => inc.id === incidentId)
    : null;

  const title = incident
    ? `${incident.severity.toUpperCase()} — ${incident.source ?? "Incident"}`
    : "Incident Detail";

  return (
    <SidePanel open={incidentId !== null} onClose={onClose} title={title}>
      {incident ? (
        <IncidentDetail incident={incident} />
      ) : (
        <p className="text-sm text-[var(--muted)]">Incident not found.</p>
      )}
    </SidePanel>
  );
}
