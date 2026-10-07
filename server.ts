import express, { Request, Response } from "express";
import cors from "cors";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROJECT_ROOT = __dirname;

const app = express();
const PORT = 3000;
const HOST = "0.0.0.0";

app.use(cors());
app.use(express.json());

// In-memory Ops State
const ALLOWED_INCIDENTS = new Set(["normal", "traffic_spike", "db_errors", "recovery"]);

function utcNow(): string {
  return new Date().toISOString();
}

interface TimelineItem {
  time: string;
  event: string;
}

interface OpsState {
  incident: string;
  updated_at: string;
  timeline: TimelineItem[];
}

const opsState: OpsState = {
  incident: "normal",
  updated_at: utcNow(),
  timeline: [
    {
      time: utcNow(),
      event: "System initialized in healthy state.",
    },
  ],
};

function pushTimeline(event: string) {
  opsState.timeline.unshift({ time: utcNow(), event });
  if (opsState.timeline.length > 30) {
    opsState.timeline = opsState.timeline.slice(0, 30);
  }
  opsState.updated_at = utcNow();
}

// Rate Limiting
const requestLog = new Map<string, number[]>();
const RATE_LIMIT = 20;
const WINDOW = 60; // seconds

function checkRateLimit(ip: string): boolean {
  const now = Date.now() / 1000;
  const timestamps = (requestLog.get(ip) || []).filter((t) => now - t < WINDOW);
  if (timestamps.length >= RATE_LIMIT) {
    return false;
  }
  timestamps.push(now);
  requestLog.set(ip, timestamps);
  return true;
}

// Knowledge Base Loader
interface KbChunk {
  text: string;
  source: string;
  chunk_index: number;
}

function chunkText(text: string, chunkSize = 900, overlap = 120): string[] {
  const normalized = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .join("\n");
  if (!normalized) return [];

  const chunks: string[] = [];
  let start = 0;
  while (start < normalized.length) {
    const end = Math.min(start + chunkSize, normalized.length);
    chunks.push(normalized.slice(start, end));
    if (end === normalized.length) break;
    start = Math.max(0, end - overlap);
  }
  return chunks;
}

function loadKbChunks(): KbChunk[] {
  const chunks: KbChunk[] = [];
  const kbDirs = [
    path.join(PROJECT_ROOT, "docs", "atlaops-kb"),
    path.join(PROJECT_ROOT, "knowledge_base"),
  ];

  for (const dir of kbDirs) {
    if (!fs.existsSync(dir)) continue;
    const walk = (currentDir: string) => {
      const files = fs.readdirSync(currentDir);
      for (const file of files) {
        const fullPath = path.join(currentDir, file);
        const stat = fs.statSync(fullPath);
        if (stat.isDirectory()) {
          walk(fullPath);
        } else if (file.endsWith(".md") || file.endsWith(".txt")) {
          try {
            const relPath = path.relative(PROJECT_ROOT, fullPath).replace(/\\/g, "/");
            const content = fs.readFileSync(fullPath, "utf-8");
            const fileChunks = chunkText(content);
            fileChunks.forEach((chunk, idx) => {
              chunks.push({
                text: chunk,
                source: relPath,
                chunk_index: idx,
              });
            });
          } catch {
            // ignore read error
          }
        }
      }
    };
    walk(dir);
  }
  return chunks;
}

const fileKbChunks: KbChunk[] = loadKbChunks();
const userMemory: { doc: string; time: string }[] = [];

function tokenize(text: string): Set<string> {
  const tokens = text.toLowerCase().match(/[a-z0-9][a-z0-9_-]{2,}/g) || [];
  return new Set(tokens);
}

function retrieveKbContext(query: string, topK = 4): { context: string; sources: { source: string; chunk: number }[] } {
  if (!fileKbChunks.length) {
    return { context: "", sources: [] };
  }

  const queryTokens = tokenize(query);
  const scored = fileKbChunks.map((item) => {
    const itemTokens = tokenize(item.text);
    let intersection = 0;
    for (const t of queryTokens) {
      if (itemTokens.has(t)) intersection++;
    }
    return { score: intersection, item };
  });

  scored.sort((a, b) => b.score - a.score);
  let top = scored.filter((x) => x.score > 0).slice(0, topK).map((x) => x.item);
  if (!top.length) {
    top = fileKbChunks.slice(0, topK);
  }

  const contexts = top.map((item) => `[${item.source}#chunk-${item.chunk_index}] ${item.text}`);
  const sources = top.map((item) => ({ source: item.source, chunk: item.chunk_index }));

  return { context: contexts.join("\n\n"), sources };
}

// Dynamic Metrics
function generateMetrics() {
  const t = Date.now() / 6000.0;
  const incident = opsState.incident;

  let cpu = 42 + 8 * Math.sin(t);
  let memory = 58 + 6 * Math.cos(t / 2);
  let latency = 120 + 20 * Math.sin(t / 1.3);
  let errorRate = 0.4 + 0.2 * Math.abs(Math.sin(t / 1.1));
  let pods = 6 + Math.floor(Math.abs(Math.sin(t / 1.8)) * 2);
  let rps = 190 + Math.floor(Math.abs(Math.sin(t)) * 35);

  if (incident === "traffic_spike") {
    cpu += 35;
    latency += 120;
    errorRate += 1.4;
    pods += 5;
    rps += 340;
  } else if (incident === "db_errors") {
    cpu += 12;
    memory += 10;
    latency += 85;
    errorRate += 3.2;
  } else if (incident === "recovery") {
    cpu -= 8;
    latency -= 20;
    errorRate -= 0.2;
  }

  cpu = Math.max(5, Math.min(99, Math.round(cpu * 10) / 10));
  memory = Math.max(10, Math.min(99, Math.round(memory * 10) / 10));
  latency = Math.max(40, Math.round(latency * 10) / 10);
  errorRate = Math.max(0.0, Math.round(errorRate * 100) / 100);

  const checkoutStatus = incident === "db_errors" ? "degraded" : "healthy";
  const apiStatus = incident === "traffic_spike" || incident === "db_errors" ? "degraded" : "healthy";

  const services = [
    { name: "api-gateway", status: apiStatus, latency_ms: Math.round(latency * 0.9 * 10) / 10 },
    { name: "orders-service", status: checkoutStatus, latency_ms: latency },
    { name: "payments-worker", status: checkoutStatus, latency_ms: Math.round(latency * 1.1 * 10) / 10 },
    { name: "ops-guru-rag", status: "healthy", latency_ms: Math.round(latency * 0.75 * 10) / 10 },
  ];

  return {
    timestamp: utcNow(),
    incident,
    metrics: {
      cpu_percent: cpu,
      memory_percent: memory,
      latency_p95_ms: latency,
      error_rate_percent: errorRate,
      pod_count: pods,
      requests_per_min: rps,
    },
    services,
  };
}

function generateLogs(limit = 20): { time: string; line: string }[] {
  const incident = opsState.incident;
  const base = [
    "INFO api-gateway request completed route=/health status=200",
    "INFO orders-service cache hit ratio=0.93",
    "INFO payments-worker batch settled count=21",
    "INFO ops-guru-rag context chunks=4 retrieval_ms=41",
  ];

  if (incident === "traffic_spike") {
    base.push(
      "WARN autoscaler scale_out pods=+3 reason=cpu_above_threshold",
      "WARN api-gateway latency elevated p95=290ms",
      "ALERT cloudwatch HighRequestRate triggered"
    );
  } else if (incident === "db_errors") {
    base.push(
      "ERROR orders-db timeout query=SELECT * FROM orders",
      "ERROR payments-worker retry exhausted payment_id=py_8172",
      "ALERT cloudwatch DatabaseErrorRate triggered"
    );
  } else if (incident === "recovery") {
    base.push(
      "INFO incident-automation remediation playbook completed",
      "INFO api-gateway latency recovered p95=128ms",
      "RESOLVED cloudwatch alarms back to normal"
    );
  }

  const logs: { time: string; line: string }[] = [];
  for (let i = 0; i < limit; i++) {
    logs.push({
      time: utcNow(),
      line: base[i % base.length],
    });
  }
  return logs;
}

function buildOpsContext(): string {
  const metricsPayload = generateMetrics();
  const m = metricsPayload.metrics;
  const recentLogs = generateLogs(4);
  const recentEvents = opsState.timeline.slice(0, 3);

  const logLines = recentLogs.map((l) => l.line).join(" | ");
  const timelineLines = recentEvents.map((e) => e.event).join(" | ");

  return (
    `Incident mode: ${opsState.incident}. ` +
    `CPU=${m.cpu_percent}%, Memory=${m.memory_percent}%, ` +
    `P95 Latency=${m.latency_p95_ms}ms, Errors=${m.error_rate_percent}%, ` +
    `Pods=${m.pod_count}, RPM=${m.requests_per_min}. ` +
    `Recent timeline: ${timelineLines}. ` +
    `Recent logs: ${logLines}.`
  );
}

// API Routes
app.get("/health", (_req: Request, res: Response) => {
  const backend = process.env.GEMINI_API_KEY ? "gemini" : process.env.OPENAI_API_KEY ? "openai" : "none";
  res.json({
    status: "ok",
    backend,
    rate_limit: `${RATE_LIMIT} req/${WINDOW}s`,
    version: "4.1.0",
    incident: opsState.incident,
    kb_chunks: fileKbChunks.length,
  });
});

app.get("/ops/metrics", (_req: Request, res: Response) => {
  res.json(generateMetrics());
});

app.get("/ops/logs", (req: Request, res: Response) => {
  const rawLimit = parseInt(req.query.limit as string, 10);
  const limit = isNaN(rawLimit) ? 20 : Math.max(5, Math.min(100, rawLimit));
  res.json({ incident: opsState.incident, logs: generateLogs(limit) });
});

app.get("/ops/incidents", (_req: Request, res: Response) => {
  res.json({
    incident: opsState.incident,
    updated_at: opsState.updated_at,
    timeline: opsState.timeline,
  });
});

app.post("/ops/incidents/trigger", (req: Request, res: Response) => {
  const incidentType = (req.body?.incident_type || "").trim().toLowerCase();
  if (!ALLOWED_INCIDENTS.has(incidentType)) {
    res.status(400).json({ detail: "Unsupported incident type" });
    return;
  }

  opsState.incident = incidentType;
  if (incidentType === "traffic_spike") {
    pushTimeline("Traffic spike simulation started. Autoscaling initiated.");
  } else if (incidentType === "db_errors") {
    pushTimeline("Database error burst simulated. Checkout degradation detected.");
  } else if (incidentType === "recovery") {
    pushTimeline("Recovery workflow simulated. Services stabilizing.");
  } else {
    pushTimeline("System returned to normal baseline.");
  }

  res.json({ ok: true, incident: opsState.incident, updated_at: opsState.updated_at });
});

app.get("/ops/architecture", (_req: Request, res: Response) => {
  res.json({
    nodes: [
      "Route53",
      "CloudFront",
      "S3 Frontend",
      "API Gateway",
      "Lambda AtlaOps API",
      "OpenAI LLM",
      "Vector Store",
      "CloudWatch",
    ],
    edges: [
      ["Route53", "CloudFront"],
      ["CloudFront", "S3 Frontend"],
      ["CloudFront", "API Gateway"],
      ["API Gateway", "Lambda AtlaOps API"],
      ["Lambda AtlaOps API", "OpenAI LLM"],
      ["Lambda AtlaOps API", "Vector Store"],
      ["Lambda AtlaOps API", "CloudWatch"],
    ],
  });
});

app.get("/ops/kb/status", (_req: Request, res: Response) => {
  res.json({
    kb_chunks: fileKbChunks.length,
    file_kb_chunks: fileKbChunks.length,
    memory_chunks: userMemory.length,
  });
});

app.get("/ops/governance", (_req: Request, res: Response) => {
  res.json({
    finops: {
      budget_usd: 120.0,
      actual_spend_usd: 34.2,
      projected_spend_usd: 48.5,
      runway_days: 21,
      cache_savings_usd: 48.2,
      services: [
        { service: "Amazon Bedrock (AI)", cost_usd: 18.4, share_pct: 53.8, trend: "+4%" },
        { service: "CloudFront & Edge CDN", cost_usd: 8.1, share_pct: 23.7, trend: "-2%" },
        { service: "CloudWatch & Real User RUM", cost_usd: 4.8, share_pct: 14.0, trend: "flat" },
        { service: "S3 Origin Storage", cost_usd: 1.9, share_pct: 5.6, trend: "flat" },
        { service: "Grafana Synthetics", cost_usd: 1.0, share_pct: 2.9, trend: "flat" },
      ],
    },
    guardrails: {
      pii_redacted_count: 1420,
      prompt_injections_blocked: 28,
      jailbreak_deflections: 14,
      model_fallback_triggers: 3,
      semantic_cache_hit_rate: 64.2,
      latency_overhead_ms: 12.4,
    },
    slo: {
      target_pct: 99.9,
      current_7d_pct: 99.95,
      allowed_downtime_mins: 43.2,
      consumed_downtime_mins: 4.6,
      remaining_error_budget_pct: 89.3,
      burn_rate: 0.24,
      status: "Healthy",
    },
    compliance: {
      tls_version: "TLS 1.3 Strict",
      waf_rules_active: 8,
      data_residency: "ap-south-1 (Mumbai Primary) & us-east-1 (AI Inference)",
      iam_role: "arn:aws:iam::123456789012:role/AtlaOpsObserver-ReadOnly",
      cron_cadence: "15-minute GitHub Action (cron: '*/15 * * * *')",
    },
  });
});

app.post("/ops/probes/run", (_req: Request, res: Response) => {
  const domains = ["atla.in", "gita.atla.in", "gate.atla.in", "obs.atla.in", "games.atla.in", "aif.atla.in"];
  const regions = [
    { id: "ap-south-1", name: "Mumbai, India", baseLatency: 38 },
    { id: "us-east-1", name: "N. Virginia, USA", baseLatency: 175 },
    { id: "eu-central-1", name: "Frankfurt, Germany", baseLatency: 128 },
  ];

  const results = domains.map((domain) => {
    const regionalProbes = regions.map((reg) => {
      const jitter = Math.floor(Math.random() * 20) - 10;
      const latency = Math.max(18, reg.baseLatency + jitter);
      return {
        region_id: reg.id,
        region_name: reg.name,
        dns_ms: Math.round(latency * 0.14 * 10) / 10,
        tls_ms: Math.round(latency * 0.22 * 10) / 10,
        ttfb_ms: Math.round(latency * 0.64 * 10) / 10,
        total_ms: latency,
        status_code: 200,
        probe_state: "healthy",
      };
    });

    return {
      domain,
      overall_status: "up",
      probes: regionalProbes,
      avg_latency_ms: Math.round(regionalProbes.reduce((acc, p) => acc + p.total_ms, 0) / regionalProbes.length),
    };
  });

  res.json({
    executed_at: utcNow(),
    probes_run: domains.length * regions.length,
    results,
  });
});

app.get("/ops/service-matrix", (_req: Request, res: Response) => {
  res.json({
    subdomains: [
      {
        domain: "atla.in",
        name: "Personal Portfolio",
        type: "Frontend / Static Export",
        services: ["CloudFront CDN", "S3 Origin", "AWS WAF", "Grafana Synthetics", "CloudWatch RUM"],
        framework: "Next.js",
        cost_tier: "Free Tier / S3",
        owner: "Sai Pranav Atla",
      },
      {
        domain: "gita.atla.in",
        name: "Gita AI Wisdom",
        type: "RAG & Semantic Retrieval",
        services: ["Amazon Nova Lite", "Titan Text Embeddings v2", "Vector Store", "OpenSearch", "Bedrock"],
        framework: "FastAPI + Vector RAG",
        cost_tier: "Bedrock Inference",
        owner: "Sai Pranav Atla",
      },
      {
        domain: "gate.atla.in",
        name: "Enterprise LLM Gateway",
        type: "Security & AI Governance Proxy",
        services: ["Semantic Caching", "PII Sanitizer", "Prompt Guardrails", "Rate Limiter", "Audit Logger"],
        framework: "Gateway Proxy",
        cost_tier: "Cache Optimized",
        owner: "Sai Pranav Atla",
      },
      {
        domain: "obs.atla.in",
        name: "Observability Deck",
        type: "Telemetry & SRE Platform",
        services: ["Express Node.js", "Prometheus Collector", "GitHub Actions cron", "CloudWatch Metrics"],
        framework: "Express + TypeScript",
        cost_tier: "Containerized",
        owner: "Sai Pranav Atla",
      },
      {
        domain: "games.atla.in",
        name: "Interactive Arcade",
        type: "WebGL Game Engine",
        services: ["CloudFront Edge", "S3 Storage", "WebSockets", "AWS WAF"],
        framework: "HTML5 / Canvas",
        cost_tier: "CDN Edge",
        owner: "Sai Pranav Atla",
      },
      {
        domain: "aif.atla.in",
        name: "AI Financial Platform",
        type: "Full-Stack AI Application",
        services: ["Amazon Bedrock", "Claude 3.5 Sonnet", "FastAPI", "DynamoDB", "VPC", "CloudWatch"],
        framework: "FastAPI + React",
        cost_tier: "On-Demand Tokens",
        owner: "Sai Pranav Atla",
      },
    ],
  });
});

app.get("/ops/incidents/rca", (_req: Request, res: Response) => {
  const incident = opsState.incident;
  const metrics = generateMetrics().metrics;
  const recentLogs = generateLogs(8).map((entry) => entry.line);
  const recentEvents = opsState.timeline.slice(0, 4).map((entry) => entry.event);

  let summary: string;
  let likelyRootCause: string;
  let mitigation: string[];

  if (incident === "traffic_spike") {
    summary = "Traffic surge caused latency amplification and autoscaling pressure.";
    likelyRootCause = "Request rate exceeded baseline, saturating API gateway and service pods.";
    mitigation = [
      "Scale out stateless services and verify autoscaler thresholds.",
      "Apply temporary rate limiting for abusive clients.",
      "Tune cache and edge TTL for high-read paths.",
    ];
  } else if (incident === "db_errors") {
    summary = "Checkout path degradation driven by database timeouts.";
    likelyRootCause = "Orders database query latency and retries increased error propagation.";
    mitigation = [
      "Investigate slow queries and connection pool saturation.",
      "Enable circuit-breaker behavior for failing DB dependencies.",
      "Shift read-heavy paths to cache and validate retry/backoff config.",
    ];
  } else if (incident === "recovery") {
    summary = "System is in recovery mode after mitigation workflow.";
    likelyRootCause = "Prior incident signals are stabilizing after remediation actions.";
    mitigation = [
      "Keep elevated monitoring until latency and error trends fully normalize.",
      "Run post-incident validation checks on dependent services.",
      "Document timeline and finalize postmortem actions.",
    ];
  } else {
    summary = "No active incident detected; platform is operating at baseline.";
    likelyRootCause = "N/A";
    mitigation = [
      "Maintain baseline observability and alert hygiene.",
      "Run periodic failure drills to validate runbooks.",
      "Review capacity thresholds before peak traffic windows.",
    ];
  }

  res.json({
    incident,
    generated_at: utcNow(),
    summary,
    likely_root_cause: likelyRootCause,
    signals: {
      cpu_percent: metrics.cpu_percent,
      memory_percent: metrics.memory_percent,
      latency_p95_ms: metrics.latency_p95_ms,
      error_rate_percent: metrics.error_rate_percent,
      pod_count: metrics.pod_count,
      requests_per_min: metrics.requests_per_min,
    },
    recent_events: recentEvents,
    recent_logs: recentLogs,
    mitigation_plan: mitigation,
  });
});

app.post("/generate/", async (req: Request, res: Response) => {
  try {
    const clientIp = (req.headers["x-forwarded-for"] as string) || req.socket.remoteAddress || "unknown";
    if (!checkRateLimit(clientIp)) {
      res.status(429).json({ detail: "Too many requests. Please slow down." });
      return;
    }

    const prompt = (req.body?.prompt || "").trim();
    if (!prompt) {
      res.status(400).json({ detail: "Prompt is required." });
      return;
    }

    const opsContext = buildOpsContext();
    const { context: kbContext, sources } = retrieveKbContext(prompt, 4);
    const memoryContext = userMemory.slice(0, 2).map((m) => m.doc).join("\n");

    const systemPrompt =
      "You are AtlaOps Guru, an AI cloud operations assistant built by Sai Pranav Atla. " +
      "Give concise, technically precise answers. " +
      "When knowledge-base context is provided, ground your answer in it and reference evidence briefly.";

    const fullPrompt =
      `Current ops state:\n${opsContext}\n\n` +
      `Knowledge base context:\n${kbContext || "No KB chunks found."}\n\n` +
      `Conversation memory:\n${memoryContext || "No prior memory found."}\n\n` +
      `User question: ${prompt}\n\n` +
      "Instructions: use the context above when relevant, be explicit about incident signals, " +
      "and avoid claims not supported by the provided context.";

    let aiResponse = "";

    if (process.env.GEMINI_API_KEY) {
      try {
        const { GoogleGenAI } = await import("@google/genai");
        const ai = new GoogleGenAI();
        const response = await ai.models.generateContent({
          model: "gemini-2.5-flash",
          contents: `${systemPrompt}\n\n${fullPrompt}`,
        });
        aiResponse = response.text || "No response received.";
      } catch (err: any) {
        aiResponse = `[AtlaOps Guru]: Operating in '${opsState.incident}' mode. Grounded knowledge base context:\n\n${kbContext.slice(0, 450)}...`;
      }
    } else if (process.env.OPENAI_API_KEY) {
      // If user supplies OpenAI key in env
      aiResponse = `OpenAI API integration active. Grounded answer based on KB: ${kbContext.slice(0, 200)}...`;
    } else {
      // Grounded offline responder
      aiResponse = `[AtlaOps Guru]: Current incident is '${opsState.incident}'. ${opsContext}\n\nContext excerpt: ${kbContext.slice(0, 300)}...`;
    }

    userMemory.unshift({
      doc: `User asked: ${prompt}. AtlaOps Guru replied: ${aiResponse}`,
      time: utcNow(),
    });
    if (userMemory.length > 20) userMemory.pop();

    res.json({
      response: aiResponse,
      sources,
      incident: opsState.incident,
    });
  } catch (exc: any) {
    res.json({
      response: `Ops Guru backend error: ${exc?.message || "Internal error"}`,
      sources: [],
      incident: opsState.incident,
    });
  }
});

// Serve static files from root (including index.html, status.json, and assets)
app.use(express.static(PROJECT_ROOT));

// Fallback to index.html for root or SPA paths
app.get("*", (_req: Request, res: Response) => {
  const indexPath = path.join(PROJECT_ROOT, "index.html");
  if (fs.existsSync(indexPath)) {
    res.sendFile(indexPath);
  } else {
    res.json({ message: "AtlaOps backend is running." });
  }
});

app.listen(PORT, HOST, () => {
  console.log(`Server listening on http://${HOST}:${PORT}`);
});
