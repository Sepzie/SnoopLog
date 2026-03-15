"use client";

import { useLiveData } from "./live-data";

export function ConnectionStatus() {
  const { connectionState: state, lastError } = useLiveData();

  const dotClass =
    state === "connected"
      ? "bg-emerald-400"
      : state === "checking"
        ? "bg-amber-400"
        : "bg-red-400";

  const label =
    state === "connected"
      ? "Connected"
      : state === "checking"
        ? "Checking..."
        : "Disconnected";

  return (
    <span
      title={lastError ?? undefined}
      className="inline-flex items-center gap-1.5 text-xs text-[var(--muted)]"
    >
      <span
        className={`h-2 w-2 rounded-full ${dotClass}`}
      />
      <span className="font-medium">{label}</span>
    </span>
  );
}
