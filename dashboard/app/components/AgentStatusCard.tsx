"use client";

import { useAgentStatus } from "../hooks/useAgentStatus";

type AgentStatusCardProps = {
  onOpenTrail: () => void;
};

export function AgentStatusCard({ onOpenTrail }: AgentStatusCardProps) {
  const status = useAgentStatus();
  const isActive = status === "investigating";

  return (
    <button
      type="button"
      onClick={onOpenTrail}
      className="group w-full rounded-2xl border border-black/8 bg-white px-4 py-4 text-left shadow-[0_8px_30px_rgba(20,20,20,0.04)] transition-all hover:border-[var(--accent)]/20 hover:shadow-[0_8px_30px_rgba(95,111,255,0.08)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm text-[#666372]">Agent Status</p>
          <div className="mt-3 flex items-center gap-2.5">
            <span
              className={`inline-block h-2.5 w-2.5 rounded-full ${
                isActive
                  ? "agent-investigating bg-[var(--accent)]"
                  : "bg-[#c4c2cc]"
              }`}
            />
            <p
              className={`text-lg font-semibold tracking-[-0.02em] capitalize ${
                isActive ? "text-[var(--accent)]" : "text-[#8d8a98]"
              }`}
            >
              {status}
            </p>
          </div>
        </div>
        <span className="rounded-full bg-[#f4f7ff] px-2 py-1 text-xs font-medium text-[#5c67c7] opacity-0 transition-opacity group-hover:opacity-100">
          trail
        </span>
      </div>
    </button>
  );
}
