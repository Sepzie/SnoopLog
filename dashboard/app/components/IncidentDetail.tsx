"use client";

import { type ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import type { IncidentFeedItem } from "./incidentTypes";

type IncidentDetailProps = {
  incident: IncidentFeedItem;
};

/* ── Markdown components for styled rendering ── */
const mdComponents: ComponentPropsWithoutRef<typeof ReactMarkdown>["components"] =
  {
    p: ({ children }) => (
      <p className="mb-2 leading-relaxed last:mb-0">{children}</p>
    ),
    strong: ({ children }) => (
      <strong className="font-semibold text-slate-900">{children}</strong>
    ),
    em: ({ children }) => <em className="text-slate-600">{children}</em>,
    code: ({ children, className }) => {
      const isBlock = className?.includes("language-");
      if (isBlock) {
        return (
          <code className="block whitespace-pre-wrap break-words text-[12.5px] leading-relaxed text-slate-800">
            {children}
          </code>
        );
      }
      return (
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[12.5px] text-rose-700">
          {children}
        </code>
      );
    },
    pre: ({ children }) => (
      <pre className="my-2 overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-3 font-mono text-[12.5px] leading-relaxed last:mb-0">
        {children}
      </pre>
    ),
    ul: ({ children }) => (
      <ul className="mb-2 ml-4 list-disc space-y-1 last:mb-0">{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className="mb-2 ml-4 list-decimal space-y-1 last:mb-0">
        {children}
      </ol>
    ),
    li: ({ children }) => <li className="leading-relaxed">{children}</li>,
    a: ({ children, href }) => (
      <a
        href={href}
        className="text-indigo-600 underline decoration-indigo-300 hover:text-indigo-800"
        target="_blank"
        rel="noopener noreferrer"
      >
        {children}
      </a>
    ),
  };

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-slate-400">
      {children}
    </p>
  );
}

function Md({ text }: { text: string }) {
  return (
    <div className="text-[13.5px] text-slate-700">
      <ReactMarkdown components={mdComponents}>{text}</ReactMarkdown>
    </div>
  );
}

export function IncidentDetail({ incident }: IncidentDetailProps) {
  const summaryText = incident.report ?? incident.summary;
  const rootCauseText = incident.rootCause ?? "Root cause pending analysis.";
  const suggestedFixText =
    incident.suggestedFix ?? "Suggested fix pending analysis.";
  const occurrenceCount =
    incident.occurrenceCount ??
    incident.logCount ??
    incident.relatedLogIds.length ??
    1;
  const codeRefs = incident.codeRefs.length
    ? incident.codeRefs
    : [{ file: "unknown", line: undefined, blame: "blame unavailable" }];
  const contextEvents = incident.contextEvents.length
    ? incident.contextEvents
    : incident.primaryEvent
      ? [incident.primaryEvent]
      : [];

  return (
    <div className="space-y-4 text-sm">
      {/* ── Summary ── */}
      <div className="rounded-xl border border-slate-200/80 bg-white p-4 text-[14px] leading-relaxed text-slate-700 shadow-sm">
        <Md text={summaryText} />
      </div>

      {/* ── Metadata pills ── */}
      <div className="grid grid-cols-3 gap-2.5">
        <div className="rounded-xl border border-slate-200/70 bg-white p-3">
          <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-400">
            Source
          </p>
          <p className="mt-1.5 text-sm font-semibold text-slate-800">
            {incident.source ?? "unknown"}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200/70 bg-white p-3">
          <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-400">
            Occurrences
          </p>
          <p className="mt-1.5 text-sm font-semibold text-slate-800">
            {occurrenceCount}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200/70 bg-white p-3">
          <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-400">
            Urgency
          </p>
          <p className="mt-1.5 text-sm font-semibold capitalize text-slate-800">
            {incident.investigationUrgency ?? "unknown"}
          </p>
        </div>
      </div>

      {/* ── Investigation trigger ── */}
      {incident.investigationReason ? (
        <div className="flex items-start gap-2.5 rounded-xl border border-indigo-100 bg-indigo-50/60 px-4 py-3">
          <span className="mt-0.5 text-indigo-400">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" />
              <path d="M8 5v3.5M8 10.5v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </span>
          <p className="text-[13px] text-indigo-800">
            {incident.investigationReason}
          </p>
        </div>
      ) : null}

      {/* ── Root cause ── */}
      <div className="rounded-xl border border-rose-200/70 bg-rose-50/50 p-4">
        <SectionLabel>Root Cause</SectionLabel>
        <div className="text-rose-900">
          <Md text={rootCauseText} />
        </div>
      </div>

      {/* ── Code references ── */}
      <div className="space-y-2">
        {codeRefs.map((ref, index) => {
          const location = `${ref.file}${ref.line ? `:${ref.line}` : ""}`;
          return (
            <div
              key={`${location}-${index}`}
              className="overflow-hidden rounded-xl border border-slate-200/70 bg-white"
            >
              <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/80 px-3.5 py-2">
                <span className="font-mono text-[12px] font-medium text-sky-700">
                  {location}
                </span>
                {ref.blame && ref.blame !== "unknown" && (
                  <span className="text-[11px] text-slate-400">
                    blame: {ref.blame}
                  </span>
                )}
              </div>
              {ref.snippet ? (
                <pre className="overflow-x-auto px-3.5 py-2.5 font-mono text-[12px] leading-relaxed text-slate-600">
                  {ref.snippet}
                </pre>
              ) : null}
            </div>
          );
        })}
      </div>

      {/* ── Suggested fix ── */}
      <div className="rounded-xl border border-emerald-200/70 bg-emerald-50/50 p-4">
        <SectionLabel>Suggested Fix</SectionLabel>
        <div className="text-emerald-900">
          <Md text={suggestedFixText} />
        </div>
      </div>

      {/* ── Context events ── */}
      {contextEvents.length > 0 && (
        <div className="rounded-xl border border-slate-200/70 bg-white p-4">
          <SectionLabel>Context Events</SectionLabel>
          <div className="mt-1 space-y-1.5">
            {contextEvents.map((event) => (
              <div
                key={event.id}
                className="rounded-lg border border-slate-100 bg-slate-50/70 px-3 py-2 font-mono text-[12px]"
              >
                <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.12em] text-slate-400">
                  <span>{event.level ?? "unknown"}</span>
                  <span className="text-slate-300">/</span>
                  <span>{event.tier ?? "unknown"}</span>
                  <span className="text-slate-300">/</span>
                  <span>
                    score{" "}
                    {typeof event.score === "number"
                      ? event.score.toFixed(2)
                      : "n/a"}
                  </span>
                </div>
                <p className="mt-1.5 text-slate-600">
                  {event.message ?? "(no message)"}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Related log IDs ── */}
      {incident.relatedLogIds.length > 0 && (
        <div className="rounded-xl border border-slate-200/70 bg-white p-4">
          <SectionLabel>Related Log IDs</SectionLabel>
          <div className="mt-1 flex flex-wrap gap-1.5 font-mono text-[11px] text-slate-500">
            {incident.relatedLogIds.map((id) => (
              <span
                key={id}
                className="rounded-md border border-slate-150 bg-slate-50 px-2 py-0.5"
              >
                {id}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
