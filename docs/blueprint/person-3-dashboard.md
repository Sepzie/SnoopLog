# Person 3: Dashboard — Implementation Spec

## InteliLog | HackTheBreak 2026

---

## Your role

You own the visual layer. You build the Next.js dashboard on Vercel that displays the live pipeline in real-time and shows incident reports. This is also the primary demo surface for judges — if the dashboard looks good and clearly shows the intelligence pipeline working, the demo lands.

---

## Deliverables

1. **Live pipeline view** — real-time log stream with anomaly scores and tier routing
2. **Incident feed** — list of AI-generated incident reports
3. **Incident detail view** — full report with agent reasoning chain and code references
4. **Pipeline stats bar** — processing counts, tier distribution, cost savings
5. **WebSocket client** — connects to the pipeline backend for real-time data

---

## Tech stack

- **Next.js 14+** (App Router) on Vercel
- **WebSocket** (or Server-Sent Events) for real-time data from the GCP backend
- **Tailwind CSS** for styling
- **shadcn/ui** components if you want pre-built UI elements
- No additional charting library needed — keep it simple with CSS-based indicators

---

## 1. WebSocket client

The pipeline backend (FastAPI on GCP) will expose a WebSocket endpoint that emits events as logs flow through the system.

### Events you'll receive

```typescript
// Every log that enters the system (including filtered)
type LogScoredEvent = {
  type: 'log:scored';
  data: LogEvent; // Full shared schema
};

// When the cheap model makes a triage decision
type LogTriagedEvent = {
  type: 'log:triaged';
  data: LogEvent & { triage: { escalate: boolean; reason: string; urgency: string } };
};

// Real-time agent tool calls during investigation
type AgentToolCallEvent = {
  type: 'agent:tool_call';
  data: {
    logId: string;
    tool: string;       // 'read_file' | 'grep_code' | 'git_blame' | etc.
    args: object;
    result: string;     // Truncated result
  };
};

// Final incident report
type IncidentCreatedEvent = {
  type: 'incident:created';
  data: LogEvent; // With incident field populated
};
```

### Connection setup

```typescript
// hooks/useWebSocket.ts
import { useEffect, useRef, useState, useCallback } from 'react';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:3001/ws';

export function usePipelineSocket() {
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [agentActivity, setAgentActivity] = useState<AgentToolCall[]>([]);
  const [stats, setStats] = useState({
    total: 0, filtered: 0, low: 0, medium: 0, high: 0, incidents: 0
  });
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      switch (msg.type) {
        case 'log:scored':
          setLogs(prev => [msg.data, ...prev].slice(0, 200)); // Keep last 200
          setStats(prev => ({
            ...prev,
            total: prev.total + 1,
            filtered: prev.filtered + (msg.data.pipeline.filtered ? 1 : 0),
            [msg.data.pipeline.tier]: prev[msg.data.pipeline.tier] + 1
          }));
          break;

        case 'agent:tool_call':
          setAgentActivity(prev => [msg.data, ...prev].slice(0, 50));
          break;

        case 'incident:created':
          setIncidents(prev => [msg.data, ...prev]);
          setStats(prev => ({ ...prev, incidents: prev.incidents + 1 }));
          break;
      }
    };

    ws.onclose = () => {
      // Reconnect after 3 seconds
      setTimeout(() => { /* re-init */ }, 3000);
    };

    return () => ws.close();
  }, []);

  return { logs, incidents, agentActivity, stats };
}
```

### Fallback: polling

If WebSocket setup is taking too long, fall back to polling a REST endpoint every 2 seconds:

```
GET /api/pipeline/recent?since={timestamp}
```

Get the real-time view working first, optimize later.

---

## 2. Page layout

Single-page dashboard with three main sections. No routing needed — keep it simple.

```
┌─────────────────────────────────────────────────────┐
│  InteliLog            [stats bar: counts + tiers]   │
├──────────────────────┬──────────────────────────────┤
│                      │                              │
│   Live log stream    │   Incident feed              │
│   (scrolling list)   │   (cards with summaries)     │
│                      │                              │
│                      │   ┌────────────────────────┐ │
│                      │   │ Incident detail         │ │
│                      │   │ (expanded on click)     │ │
│                      │   │                         │ │
│                      │   │ Agent reasoning chain   │ │
│                      │   │ Code references         │ │
│                      │   │ Suggested fix           │ │
│                      │   └────────────────────────┘ │
│                      │                              │
├──────────────────────┴──────────────────────────────┤
│  Agent activity feed (real-time tool calls)         │
└─────────────────────────────────────────────────────┘
```

---

## 3. Live log stream

A scrolling list of logs as they flow through the pipeline. Each row shows:

- Timestamp
- Log level (color-coded: info=gray, warn=amber, error=red, fatal=red-bold)
- Anomaly score (0.0-1.0 as a small colored bar: green < 0.3, amber 0.3-0.7, red > 0.7)
- Tier assignment (badge: "dropped", "low", "medium", "high")
- Truncated message

```tsx
function LogRow({ log }: { log: LogEvent }) {
  const scoreColor = log.pipeline.anomaly_score < 0.3
    ? 'bg-green-500'
    : log.pipeline.anomaly_score < 0.7
    ? 'bg-amber-500'
    : 'bg-red-500';

  const tierBadge = {
    low: 'bg-gray-100 text-gray-600',
    medium: 'bg-amber-100 text-amber-700',
    high: 'bg-red-100 text-red-700'
  };

  return (
    <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-100 font-mono text-sm">
      <span className="text-gray-400 text-xs w-20 shrink-0">
        {new Date(log.timestamp).toLocaleTimeString()}
      </span>

      <span className={`uppercase text-xs font-medium w-12 ${levelColor(log.level)}`}>
        {log.level}
      </span>

      {/* Anomaly score bar */}
      <div className="w-16 h-2 bg-gray-100 rounded-full overflow-hidden shrink-0">
        <div
          className={`h-full rounded-full ${scoreColor}`}
          style={{ width: `${(log.pipeline.anomaly_score || 0) * 100}%` }}
        />
      </div>

      <span className={`text-xs px-2 py-0.5 rounded ${tierBadge[log.pipeline.tier] || 'bg-gray-50'}`}>
        {log.pipeline.filtered ? 'filtered' : log.pipeline.tier}
      </span>

      <span className="text-gray-700 truncate">
        {log.message}
      </span>
    </div>
  );
}
```

### Auto-scroll behavior

The list should auto-scroll to show new logs, but pause auto-scroll if the user scrolls up to inspect older logs. Resume auto-scroll when they scroll back to the bottom.

---

## 4. Incident feed

Cards showing each incident report, most recent first.

```tsx
function IncidentCard({ incident, onClick }: { incident: LogEvent; onClick: () => void }) {
  const severityColor = {
    critical: 'border-l-red-600 bg-red-50',
    high: 'border-l-red-400 bg-red-50',
    medium: 'border-l-amber-400 bg-amber-50',
    low: 'border-l-green-400 bg-green-50',
  };

  return (
    <div
      className={`border-l-4 rounded-lg p-4 cursor-pointer hover:shadow-md transition ${severityColor[incident.incident.severity]}`}
      onClick={onClick}
    >
      <div className="flex justify-between items-start mb-2">
        <span className="text-xs font-medium uppercase tracking-wide text-gray-500">
          {incident.incident.severity}
        </span>
        <span className="text-xs text-gray-400">
          {new Date(incident.timestamp).toLocaleTimeString()}
        </span>
      </div>

      <p className="text-sm font-medium text-gray-900 mb-1">
        {incident.incident.report}
      </p>

      {incident.incident.code_refs?.length > 0 && (
        <p className="text-xs text-gray-500 font-mono">
          {incident.incident.code_refs[0].file}:{incident.incident.code_refs[0].line}
        </p>
      )}
    </div>
  );
}
```

---

## 5. Incident detail view

When an incident card is clicked, expand to show the full report.

### Sections to display

**Summary** — the `report` field, prominently displayed.

**Root cause** — the `root_cause` field with a subtle background.

**Code references** — each code ref shown as a clickable block:
```
src/db/pool.ts:42
Last changed by sepehr on 2026-03-13 (commit a1b2c3d)
```

**Suggested fix** — the `suggested_fix` field in a callout/banner.

**Agent reasoning chain** — show the tool calls the agent made during investigation, in order:
```
1. grep_code("ECONNREFUSED") → Found 3 matches
2. read_file("src/db/pool.ts", lines 35-50) → Read pool configuration
3. git_blame("src/db/pool.ts", lines 40-45) → Recent change by sepehr
4. search_logs("connection pool") → 47 related errors in last 5 min
```

This reasoning chain is crucial for the demo — it shows judges that the AI isn't a black box.

---

## 6. Pipeline stats bar

A horizontal bar at the top showing real-time counts:

```tsx
function StatsBar({ stats }) {
  return (
    <div className="flex items-center gap-6 px-6 py-3 bg-gray-50 border-b text-sm">
      <Stat label="Total logs" value={stats.total} />
      <Stat label="Filtered" value={stats.filtered} color="gray" />
      <Stat label="Low" value={stats.low} color="green" />
      <Stat label="Medium" value={stats.medium} color="amber" />
      <Stat label="High" value={stats.high} color="red" />
      <Stat label="Incidents" value={stats.incidents} color="red" />

      {/* Cost savings estimate */}
      <div className="ml-auto text-xs text-gray-500">
        Est. saved: ${((stats.filtered + stats.low) * 0.001).toFixed(2)} by not sending to LLM
      </div>
    </div>
  );
}
```

---

## 7. Agent activity feed

A smaller feed at the bottom showing real-time agent tool calls as they happen. This creates a "watching the AI think" experience that's compelling in a demo.

```tsx
function AgentActivityFeed({ activity }) {
  return (
    <div className="bg-gray-900 text-green-400 font-mono text-xs p-4 rounded-lg max-h-40 overflow-y-auto">
      {activity.map((call, i) => (
        <div key={i} className="mb-1">
          <span className="text-gray-500">[{call.tool}]</span>{' '}
          <span className="text-green-300">{formatArgs(call.args)}</span>{' '}
          <span className="text-gray-600">→ {call.result.substring(0, 80)}...</span>
        </div>
      ))}
    </div>
  );
}
```

---

## Development approach

### Start with mock data

Don't wait for the backend WebSocket. Build the entire UI with mock data first.

```typescript
// lib/mockData.ts
export function generateMockLog(): LogEvent {
  const levels = ['info', 'info', 'info', 'warn', 'error'];
  const level = levels[Math.floor(Math.random() * levels.length)];
  const score = level === 'error' ? 0.5 + Math.random() * 0.5 : Math.random() * 0.4;

  return {
    id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    level,
    message: generateRandomLogMessage(level),
    source: 'dummy-ecommerce-api',
    pipeline: {
      anomaly_score: score,
      tier: score < 0.3 ? 'low' : score < 0.7 ? 'medium' : 'high',
      filtered: false
    }
  };
}

// Simulate logs arriving every 500ms
export function startMockStream(callback: (log: LogEvent) => void) {
  return setInterval(() => callback(generateMockLog()), 500);
}
```

### Switch to real WebSocket when backend is ready

The `usePipelineSocket` hook is already structured to accept real data. Just update `WS_URL` to point at the GCP backend.

---

## File structure

```
/dashboard
  /app
    page.tsx              # Main dashboard page
    layout.tsx            # Root layout with fonts/metadata
    globals.css           # Tailwind imports
  /components
    StatsBar.tsx          # Pipeline statistics
    LogStream.tsx         # Live log feed
    LogRow.tsx            # Individual log row
    IncidentFeed.tsx      # Incident card list
    IncidentCard.tsx      # Summary card
    IncidentDetail.tsx    # Expanded report view
    AgentActivity.tsx     # Real-time agent tool calls
  /hooks
    usePipelineSocket.ts  # WebSocket connection + state
  /lib
    types.ts              # TypeScript types matching shared schema
    mockData.ts           # Mock data generators for development
  next.config.js
  tailwind.config.ts
  package.json
```

---

## Styling guidelines

- **Dark header** with InteliLog branding, light body
- **Monospace font** for log messages and agent activity (JetBrains Mono or similar)
- **Color-coded severity** consistently across all components
- **Minimal animations** — a subtle fade-in for new logs is fine, nothing flashy
- Keep it clean and professional. Judges are technical; they'll appreciate clarity over decoration.

---

## Coordination with other tracks

- **Person 1 & 2** provide the event stream. Agree on the WebSocket endpoint URL and event format early.
- **Person 4** will deploy the backend — coordinate on the WebSocket URL for the Vercel deployment's environment variable.
- You can develop fully independently using mock data until the backend is ready.

---

## Priority order

1. Scaffold Next.js project, deploy to Vercel, get a blank page live (30 min)
2. Build the LogStream component with mock data (1 hour)
3. Build the StatsBar (30 min)
4. Build the IncidentFeed and IncidentCard (1 hour)
5. Build the IncidentDetail view (1 hour)
6. Build the AgentActivity feed (30 min)
7. Implement the WebSocket hook with real backend connection (1 hour)
8. Polish layout, responsive behavior, demo readiness (remaining time)

