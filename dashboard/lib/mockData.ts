export type MockTier = "low" | "medium" | "high";
export type MockLevel = "info" | "warn" | "error";

export type MockLogEvent = {
  id: string;
  timestamp: string;
  source: string;
  level: MockLevel;
  message: string;
  pipeline: {
    anomaly_score: number;
    tier: MockTier;
    filtered: boolean;
  };
};

export type MockIncident = {
  id: string;
  timestamp: string;
  severity: "medium" | "high" | "critical";
  summary: string;
  rootCause: string;
  codeRefs: Array<{ file: string; line: number }>;
  suggestedFix: string;
};

export type MockAgentCall = {
  id: string;
  timestamp: string;
  command: string;
  toolName: string;
  args: string;
  result: string;
  ok: boolean;
};

const INFO_MESSAGES = [
  "GET /api/products 200 in 38ms",
  "Cache hit for catalog:featured",
  "Worker heartbeat OK",
  "Session refresh completed",
];

const WARN_MESSAGES = [
  "Retrying Redis connection (attempt 2/5)",
  "Payment provider latency > 800ms",
  "Queue depth above warning threshold",
  "DB pool saturation at 78%",
];

const ERROR_MESSAGES = [
  "POST /checkout failed: payment provider timeout",
  "Unhandled exception in order processor",
  "Database write failed: deadlock detected",
  "Webhook delivery failed after retries",
];

const AGENT_TOOL_CALLS = [
  {
    toolName: "search_logs",
    args: '{"query": "payment timeout", "limit": 50}',
    result: '{"matches": 12, "summary": "Found 12 payment timeout errors in the last hour, primarily from checkout-service. Peak at 14:32 UTC."}',
  },
  {
    toolName: "grep_code",
    args: '{"pattern": "createPaymentIntent", "file_glob": "*.ts"}',
    result: 'services/payment/client.ts:88:  const intent = await createPaymentIntent(amount, currency);\nservices/payment/client.ts:142:  // createPaymentIntent wrapper with no timeout\nservices/checkout/handler.ts:55:  const result = await paymentClient.createPaymentIntent(order.total, order.currency);',
  },
  {
    toolName: "read_file",
    args: '{"path": "services/payment/client.ts", "start_line": 70, "end_line": 110}',
    result: '70: export class PaymentClient {\n71:   private stripe: Stripe;\n72: \n73:   constructor(apiKey: string) {\n74:     this.stripe = new Stripe(apiKey);\n75:   }\n76: \n77:   async createPaymentIntent(amount: number, currency: string) {\n78:     // No timeout configured - this can hang indefinitely\n79:     const intent = await this.stripe.paymentIntents.create({\n80:       amount,\n81:       currency,\n82:       automatic_payment_methods: { enabled: true },\n83:     });\n84:     return intent;\n85:   }',
  },
  {
    toolName: "git_blame",
    args: '{"path": "services/payment/client.ts", "start_line": 88, "end_line": 88}',
    result: 'a3f2c91d (dev-jane 2025-11-03 09:14:22 +0000 88)     const intent = await this.stripe.paymentIntents.create({',
  },
  {
    toolName: "report_incident",
    args: '{"severity": "high", "confidence": 0.93}',
    result: '{"status": "created", "incident_id": "INC-2847", "summary": "Payment timeout causing checkout failures"}',
  },
];

function randomBetween(min: number, max: number): number {
  return Math.random() * (max - min) + min;
}

function pick<T>(items: T[]): T {
  return items[Math.floor(Math.random() * items.length)];
}

function chooseLevelByWeight(): MockLevel {
  const roll = Math.random();
  if (roll < 0.6) {
    return "info";
  }
  if (roll < 0.85) {
    return "warn";
  }
  return "error";
}

function tierFromScore(score: number): MockTier {
  if (score > 0.7) {
    return "high";
  }
  if (score >= 0.3) {
    return "medium";
  }
  return "low";
}

export function createMockLogEvent(): MockLogEvent {
  const level = chooseLevelByWeight();

  const score =
    level === "info"
      ? randomBetween(0.03, 0.28)
      : level === "warn"
        ? randomBetween(0.31, 0.69)
        : randomBetween(0.71, 0.98);

  const message =
    level === "info"
      ? pick(INFO_MESSAGES)
      : level === "warn"
        ? pick(WARN_MESSAGES)
        : pick(ERROR_MESSAGES);

  return {
    id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    source: "mock-service",
    level,
    message,
    pipeline: {
      anomaly_score: Number(score.toFixed(2)),
      tier: tierFromScore(score),
      filtered: Math.random() < 0.28,
    },
  };
}

export function createInitialMockLogs(count = 25): MockLogEvent[] {
  return Array.from({ length: count }, () => createMockLogEvent()).sort(
    (a, b) => b.timestamp.localeCompare(a.timestamp),
  );
}

export function createMockIncident(): MockIncident {
  const severityPool: MockIncident["severity"][] = [
    "medium",
    "high",
    "critical",
  ];
  const severity = pick(severityPool);

  return {
    id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    severity,
    summary:
      "Checkout reliability degraded due to upstream payment instability",
    rootCause: "No timeout guard on createPaymentIntent in payment client",
    codeRefs: [{ file: "services/payment/client.ts", line: 88 }],
    suggestedFix:
      "Add 3s timeout, jittered retry backoff, and a circuit breaker",
  };
}

export function createMockAgentCall(): MockAgentCall {
  const tool = pick(AGENT_TOOL_CALLS);
  const command = `${tool.toolName} ${tool.args} -> ${tool.result.slice(0, 90)}...`;
  return {
    id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    command,
    toolName: tool.toolName,
    args: tool.args,
    result: tool.result,
    ok: true,
  };
}

export function createInitialMockIncidents(count = 2): MockIncident[] {
  return Array.from({ length: count }, () => createMockIncident()).sort(
    (a, b) => b.timestamp.localeCompare(a.timestamp),
  );
}

export function createInitialMockAgentCalls(count = 5): MockAgentCall[] {
  return Array.from({ length: count }, () => createMockAgentCall()).sort(
    (a, b) => b.timestamp.localeCompare(a.timestamp),
  );
}

export function startMockLogStream(
  onLog: (event: MockLogEvent) => void,
  intervalMs = 10000,
): () => void {
  const timer = setInterval(() => {
    onLog(createMockLogEvent());
  }, intervalMs);

  return () => clearInterval(timer);
}

export function startMockIncidentStream(
  onIncident: (incident: MockIncident) => void,
  intervalMs = 30000,
): () => void {
  const timer = setInterval(() => {
    onIncident(createMockIncident());
  }, intervalMs);

  return () => clearInterval(timer);
}

export function startMockAgentCallStream(
  onCall: (call: MockAgentCall) => void,
  intervalMs = 5000,
): () => void {
  const timer = setInterval(() => {
    onCall(createMockAgentCall());
  }, intervalMs);

  return () => clearInterval(timer);
}
