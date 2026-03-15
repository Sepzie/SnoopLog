"use client";

import { useLiveData } from "./live-data";
import { SidePanel } from "./SidePanel";
import { AgentCall } from "./AgentCall";

type AgentTrailSidePanelProps = {
  open: boolean;
  onClose: () => void;
};

export function AgentTrailSidePanel({
  open,
  onClose,
}: AgentTrailSidePanelProps) {
  const { agentCalls } = useLiveData();

  return (
    <SidePanel open={open} onClose={onClose} title="Investigation Trail">
      {agentCalls.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-black/8 bg-white/60 p-4 text-sm text-[var(--muted)]">
          No agent activity yet. Tool calls will appear here when the agent
          begins investigating.
        </div>
      ) : (
        <div className="space-y-2">
          {agentCalls.map((call) => (
            <AgentCall
              key={call.id}
              command={call.command}
              toolName={call.toolName}
              args={call.args}
              result={call.result}
              ok={call.ok}
              full
            />
          ))}
        </div>
      )}
    </SidePanel>
  );
}
