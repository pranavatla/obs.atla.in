/* Architecture diagrams for obs.atla.in, shared by the 3D view (index.html) and the table view
   (classic.html). Exposes window.renderArchitecture(domain, hostElement) and window.hasArchitecture(domain).
   Every tile and arrow comes from the site's own repo; see the ARCH table below. */
(() => {
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  /* ---------- Architecture: AWS reference-style diagram per site, read from each site's repo ---------- */
  // Nested boundaries (AWS Cloud → VPC → subnets → cluster or host), service tiles with icons,
  // the main request path straight down the left, a Security & Governance row, and anything outside
  // AWS in its own box. Every tile and arrow comes from the site's repo; facts a repo doesn't state are
  // left out and named in the footnote rather than guessed.

  // Original line icons on a 24-unit grid (not AWS's icon set). Each is a list of SVG path strings.
  const ICONS = {
    users: ["M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z", "M3 19c0-3.3 2.7-5 6-5s6 1.7 6 5", "M16 5.5a2.6 2.6 0 0 1 0 5", "M17.5 14c2 .5 3.5 2 3.5 5"],
    api: ["M8 6l-5 6 5 6", "M16 6l5 6-5 6", "M14 4l-4 16"],
    dns: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M3 12h18", "M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"],
    cdn: ["M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16z", "M4.5 9h15", "M4.5 15h15", "M12 4v16"],
    bucket: ["M4 6c0-1.4 3.6-2.5 8-2.5s8 1.1 8 2.5-3.6 2.5-8 2.5S4 7.4 4 6z", "M4 6l1.8 12.5c.3 1.4 3 2.5 6.2 2.5s5.9-1.1 6.2-2.5L20 6"],
    shield: ["M12 3l7.5 3v5.5c0 4.6-3.2 8.2-7.5 9.5-4.3-1.3-7.5-4.9-7.5-9.5V6z", "M9 12l2.2 2.2L15.5 10"],
    cert: ["M5 4h14v11H5z", "M8 8h8", "M8 11h5", "M10 15l-1.5 5 3.5-2 3.5 2-1.5-5"],
    key: ["M8.5 15.5a4 4 0 1 1 3.5-6h9v3h-2v2.5h-3V12h-4a4 4 0 0 1-3.5 3.5z", "M7.5 11.5h.01"],
    lambda: ["M6 4h3l8 16h2.5", "M11.5 10.5L6 20"],
    chip: ["M7 7h10v10H7z", "M10 10h4v4h-4z", "M9.5 4v3M14.5 4v3M9.5 17v3M14.5 17v3M4 9.5h3M4 14.5h3M17 9.5h3M17 14.5h3"],
    proxy: ["M4 8h13", "M14 5l3 3-3 3", "M20 16H7", "M10 13l-3 3 3 3"],
    gateway: ["M5 20V9a7 7 0 0 1 14 0v11", "M3 20h18", "M9 20v-6h6v6"],
    db: ["M5 6c0-1.7 3.1-3 7-3s7 1.3 7 3-3.1 3-7 3-7-1.3-7-3z", "M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6", "M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"],
    cache: ["M13 3L6 13.5h5L10 21l8-11h-5z"],
    chart: ["M4 20h16", "M7 16v-4", "M11 16V8", "M15 16v-6", "M19 16V5"],
    registry: ["M4 7l8-4 8 4-8 4z", "M4 12l8 4 8-4", "M4 17l8 4 8-4"],
    iam: ["M4 5h16v14H4z", "M9.5 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4z", "M6.5 16c.4-2 1.6-3 3-3s2.6 1 3 3", "M15 9h3M15 12h3"],
    budget: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M14.8 8.5c-.6-.8-1.6-1.2-2.8-1.2-1.6 0-2.8.8-2.8 2.1 0 2.9 5.8 1.6 5.8 4.6 0 1.3-1.2 2.2-3 2.2-1.3 0-2.4-.5-3-1.4", "M12 5.5v13"],
    lock: ["M6 11h12v9H6z", "M8.5 11V8a3.5 3.5 0 0 1 7 0v3", "M12 14.5v2.5"],
    igw: ["M3 12h18", "M12 3v18", "M7 7l10 10", "M17 7L7 17"],
    pin: ["M12 21s6.5-6.1 6.5-11.2a6.5 6.5 0 0 0-13 0C5.5 14.9 12 21 12 21z", "M12 12a2.2 2.2 0 1 0 0-4.4 2.2 2.2 0 0 0 0 4.4z"],
    k8s: ["M12 3l7.5 4.2v9.6L12 21l-7.5-4.2V7.2z", "M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z", "M12 3v5.5M12 15.5V21M4.5 7.2l4.6 3M14.9 13.8l4.6 3M19.5 7.2l-4.6 3M9.1 13.8l-4.6 3"],
    pod: ["M12 3l8 4.5v9L12 21l-8-4.5v-9z", "M4 7.5l8 4.5 8-4.5", "M12 12v9"],
    lb: ["M12 4v5", "M12 9l-6 6M12 9l6 6M12 9v6", "M4 15h4v5H4zM10 15h4v5h-4zM16 15h4v5h-4z"],
    spark: ["M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z", "M18.5 15.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"],
    vector: ["M6 6h.01M12 5h.01M18 7h.01M5 12h.01M11 11h.01M17 13h.01M7 18h.01M13 17h.01M19 18h.01", "M11 11l6 2M11 11L5 12M11 11l1-6"],
    clock: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M12 7v5l3.5 2"],
    branch: ["M6 3v12", "M6 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6z", "M18 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6z", "M18 9c0 5-6 4-11.5 7"],
    pulse: ["M3 12h4l2.5-6 4 12 2.5-6H21"],
    eye: ["M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z", "M12 14.8a2.8 2.8 0 1 0 0-5.6 2.8 2.8 0 0 0 0 5.6z"],
    archive: ["M3.5 5h17v4h-17z", "M5 9v10h14V9", "M10 13h4"],
    terminal: ["M4 5h16v14H4z", "M7.5 9.5l3 2.5-3 2.5", "M12.5 15h4"],
    browser: ["M3 5h18v14H3z", "M3 9h18", "M6 7h.01M8.5 7h.01"],
    code: ["M5 4h14v16H5z", "M9.5 10l-2 2 2 2", "M14.5 10l2 2-2 2"],
    log: ["M6 3h9l4 4v14H6z", "M15 3v4h4", "M9 12h7M9 15h7M9 18h4"],
    send: ["M3 11.5L21 4l-7.5 18-2.5-7.5z", "M11 14.5L21 4"],
  };
  // Category hues, one per kind of service (networking, compute, storage, security, data, AI, ops, outside)
  const HUE = { net: "#8c4fff", compute: "#ed7100", storage: "#3f8624", sec: "#dd344c", data: "#3b48cc", ai: "#01a88d", ops: "#e7157b", ext: "#5f6b7a", user: "#5f6b7a" };

  const SEC_IAM = (s) => ({ id: "iam", i: "iam", c: "sec", t: "IAM", s });
  const SEC_ACM = (s) => ({ id: "acm", i: "cert", c: "sec", t: "ACM", s });
  const SEC_WAF = (s) => ({ id: "waf", i: "shield", c: "sec", t: "AWS WAF", s });
  const STATIC_DELIVERY = (repo, branch, role, steps, file) => ({ repo, branch, file, steps: ["Push to " + branch, "GitHub Actions", "OIDC → " + role, ...steps] });

  const ARCH = {
    "gate.atla.in": {
      summary: "One Graviton EC2 host in a public subnet, running Docker Compose. Caddy terminates TLS and proxies to the FastAPI gateway, which keeps its audit log and cache in Postgres and its rate limits in Redis, then calls Bedrock or one of three outside providers.",
      users: [{ id: "tn", i: "api", c: "user", t: "API tenants", s: "gita pods · atla.in Lambda" }, { id: "vis", i: "users", c: "user", t: "Visitors", s: "Landing page + chatbot" }],
      cloud: "AWS Cloud · ap-south-1",
      rows: [
        [{ id: "r53", i: "dns", c: "net", t: "Route 53", s: "A record → Elastic IP" }, { id: "ecr", i: "registry", c: "compute", t: "ECR", s: "gate images, immutable tags" }, { id: "ssm", i: "key", c: "sec", t: "SSM Parameters", s: "/gate/prod secrets" }, { id: "bk", i: "archive", c: "storage", t: "S3 backups", s: "Nightly Postgres dumps + deploy bundle" }, { id: "bed", i: "spark", c: "ai", t: "Bedrock", s: "Nova 2 Lite" }],
        { box: "vpc", label: "VPC gate-vpc · 10.40.0.0/16", short: "VPC · 10.40.0.0/16", rows: [
          { box: "public", label: "Public subnet gate-public-a · AZ-a", short: "Public subnet · AZ-a", rows: [
            [{ id: "igw", i: "igw", c: "net", t: "Internet GW", s: "gate-igw" }, { id: "eip", i: "pin", c: "net", t: "Elastic IP", s: "gate-host-eip" }, { id: "sg", i: "lock", c: "sec", t: "Security group", s: "In: 443 and 80 only" }],
            { box: "host", label: "EC2 t4g.small · AL2023 arm64 · Docker Compose", short: "EC2 t4g.small · Compose", rows: [
              [{ id: "caddy", i: "proxy", c: "net", t: "Caddy 2.11", s: "Let's Encrypt TLS · HSTS · 1 MB limit" }, { id: "gw", i: "gateway", c: "compute", t: "Gateway", s: "FastAPI · keys, limits, policy, failover" }],
              { heading: "Data", tiles: [{ id: "pg", i: "db", c: "data", t: "Postgres 17", s: "pgvector · audit, prices, semantic cache", w: 2 }, { id: "redis", i: "cache", c: "data", t: "Redis 7", s: "Token buckets, memory only", w: 2 }] },
              { heading: "Monitoring", tiles: [{ id: "graf", i: "chart", c: "ops", t: "Grafana 13", s: "Dashboards, eval regression alerts" }] },
            ] },
          ] },
          { note: "No private subnets and no NAT gateway: one public host, reachable only on 443 and 80." },
        ] },
      ],
      security: [SEC_IAM("Least-privilege host role"), { id: "oidc", i: "branch", c: "sec", t: "GitHub OIDC", s: "Deploy role, main branch only" }, { id: "sm", i: "terminal", c: "sec", t: "Session Manager", s: "No SSH port open" }, { id: "imds", i: "lock", c: "sec", t: "IMDSv2", s: "Tokens required" }, { id: "ebs", i: "archive", c: "sec", t: "EBS encryption", s: "Root volume encrypted" }, { id: "scan", i: "eye", c: "sec", t: "ECR scanning", s: "Scan on push" }, { id: "bud", i: "budget", c: "sec", t: "AWS Budgets", s: "gate-monthly, 80% and 100% alerts" }],
      external: { label: "Outside AWS", tiles: [{ id: "le", i: "cert", c: "ext", t: "Let's Encrypt", s: "Caddy's TLS certificates" }, { id: "ls", i: "pulse", c: "ext", t: "LangSmith", s: "Traces" }, { id: "llm", i: "spark", c: "ext", t: "Anthropic · OpenAI · Gemini", s: "Model APIs over HTTPS", w: 2 }] },
      edges: [["tn", "r53", "DNS", 1], ["vis", "r53"], ["r53", "igw", "A → EIP", 1], ["igw", "caddy", "HTTPS 443", 1], ["caddy", "gw", "proxy :8000", 1], ["gw", "pg", "audit · cache"], ["gw", "redis", "limits"], ["graf", "pg", "read-only"], ["gw", "bed", "Bedrock", 0, "r"], ["gw", "llm", "providers", 0, "r"]],
      delivery: { repo: "pranavatla/gate", branch: "main", file: "deploy.yml", steps: ["Push to main", "GitHub Actions (arm64)", "OIDC → gate-github-deploy", "Unit tests", "docker build", "ECR (immutable tag)", "S3 deploy bundle", "SSM Run Command", "Health check"] },
      extra: "Infrastructure is Terraform in infra/terraform.",
      watch: "Grafana synthetic check · /v1/stats audit totals · LangSmith traces · nightly evals 03:30 IST",
    },
    "gita.atla.in": {
      summary: "Internet-facing ALB with a regional WAF in front of an EKS cluster. The AWS Load Balancer Controller builds the ALB from the gita Ingress; the FastAPI pods serve the UI and the answer API, search an in-memory vector cache, embed with Titan on Bedrock and send chat calls through gate.atla.in.",
      users: [{ id: "u", i: "users", c: "user", t: "Readers", s: "Ask a question" }],
      cloud: "AWS Cloud · ap-south-1",
      rows: [
        [{ id: "r53", i: "dns", c: "net", t: "Route 53", s: "gita.atla.in → ALB" }, { id: "ecr", i: "registry", c: "compute", t: "ECR", s: "gita images, tagged by commit" }, { id: "bed", i: "spark", c: "ai", t: "Bedrock", s: "Titan Embed v2, direct" }],
        { box: "vpc", label: "VPC · gita-rag-cluster", rows: [
          { box: "public", label: "Public subnets", rows: [
            [{ id: "alb", i: "lb", c: "net", t: "ALB", s: "k8s-gita-gitaapp · internet-facing" }],
          ] },
          { box: "cluster", label: "EKS cluster · gita-rag-cluster", rows: [
            [{ id: "lbc", i: "k8s", c: "compute", t: "LB Controller", s: "Creates the ALB from the Ingress", col: 1 }],
            { box: "group", label: "Namespace gita · deployment", short: "Namespace gita", rows: [
              [{ id: "pod", i: "pod", c: "compute", t: "FastAPI pods", s: "uvicorn · UI + /answer API" }],
              { heading: "In the pod", tiles: [{ id: "vec", i: "vector", c: "data", t: "Vector cache", s: "Baked into the image, hybrid search + rerank", w: 2 }] },
            ] },
          ] },
        ] },
        { heading: "Monitoring", tiles: [{ id: "cw", i: "pulse", c: "ops", t: "CloudWatch", s: "ALB · WAF · Bedrock · RUM" }] },
      ],
      security: [SEC_WAF("Regional ACL gita-atla-in on the ALB"), SEC_ACM("TLS certificate for the ALB"), SEC_IAM("GitHub OIDC deploy role")],
      external: { label: "Outside this cluster", tiles: [{ id: "gate", i: "gateway", c: "ai", t: "gate.atla.in", s: "Chat → Nova 2 Lite, 3 retries" }] },
      edges: [["u", "r53", "DNS", 1], ["r53", "alb", "alias", 1], ["alb", "pod", "HTTPS → pods", 1], ["pod", "vec", "search"], ["pod", "bed", "embed", 0, "r"], ["pod", "gate", "chat", 1, "r"], ["waf", "alb", "filters", 0, "l"]],
      delivery: { repo: "pranavatla/Gita", branch: "main", file: "push-to-ecr.yml", steps: ["Push to main", "GitHub Actions", "OIDC → deploy role", "docker buildx", "ECR image:sha", "kubectl set image", "rollout status"] },
      extra: "rag-evaluation.yml scores answer quality.",
      note: "The repo doesn't record the VPC address range, node group or subnet layout, so they aren't drawn.",
      watch: "Grafana synthetic check every 10 min · CloudWatch RUM · ALB, WAF and Bedrock metrics",
    },
    "atla.in": {
      summary: "Static Next.js export on S3 behind CloudFront and WAF. The chat widget is the only dynamic path: the browser calls a Lambda Function URL, the Lambda reads the gateway key from SSM and forwards the question to gate.atla.in.",
      users: [{ id: "u", i: "users", c: "user", t: "Visitors", s: "Pages + chat widget" }],
      cloud: "AWS Cloud",
      rows: [
        [{ id: "r53", i: "dns", c: "net", t: "Route 53", s: "atla.in hosted zone" }, { id: "cf", i: "cdn", c: "net", t: "CloudFront", s: "E2OMRFTQ27WGMZ · free plan" }, { id: "s3", i: "bucket", c: "storage", t: "S3", s: "Next.js static export" }],
        { box: "serverless", label: "Serverless · no VPC · ap-south-1", short: "Serverless · no VPC", rows: [
          [{ id: "fn", i: "lambda", c: "compute", t: "Lambda", s: "atla-chatbot · Python 3.13 · Function URL" }, { id: "ssm", i: "key", c: "sec", t: "SSM Parameter", s: "/atla-chatbot/prod/GATE_API_KEY" }],
        ] },
        { heading: "Monitoring", tiles: [{ id: "cw", i: "pulse", c: "ops", t: "CloudWatch", s: "CloudFront · WAF · RUM · Lambda logs" }] },
      ],
      security: [SEC_WAF("Free-plan ACL on CloudFront"), SEC_ACM("TLS certificate for CloudFront"), SEC_IAM("GitHub OIDC deploy role"), { id: "cors", i: "lock", c: "sec", t: "CORS + concurrency", s: "Only atla.in may call; reserved concurrency caps cost" }],
      external: { label: "Outside AWS", tiles: [{ id: "gate", i: "gateway", c: "ai", t: "gate.atla.in", s: "Tenant: atla.in chatbot → Nova 2 Lite" }] },
      edges: [["u", "r53", "DNS", 1], ["r53", "cf", "alias", 1], ["cf", "s3", "origin", 1], ["u", "fn", "POST chat", 1, "l"], ["fn", "ssm", "reads key"], ["fn", "gate", "Bearer key", 1, "l"]],
      delivery: STATIC_DELIVERY("pranavatla/ai_agent_1", "develop", "deploy role", ["npm ci + next build", "s3 sync out/", "CloudFront invalidation", "Grafana deploy marker"], "deploy-frontend-aws.yml"),
      extra: "The chatbot Lambda is Terraform in pranavatla/gate (examples/atla-chatbot).",
      watch: "Grafana synthetic check every 5 min from 3 probes · CloudWatch RUM · CloudFront and WAF metrics",
    },
    "obs.atla.in": {
      summary: "This page. CloudFront and WAF in front of a private S3 bucket that holds the HTML and status.json. Every 15 minutes an EventBridge rule starts the collector on GitHub Actions, which reads Grafana Cloud, CloudWatch and the gateway, then writes a fresh status.json to the bucket.",
      users: [{ id: "u", i: "browser", c: "user", t: "Your browser", s: "Three.js scene" }],
      cloud: "AWS Cloud",
      rows: [
        [{ id: "r53", i: "dns", c: "net", t: "Route 53", s: "obs.atla.in → CloudFront" }, { id: "cf", i: "cdn", c: "net", t: "CloudFront", s: "E2EXL4C10F3QBA · free plan" }, { id: "s3", i: "bucket", c: "storage", t: "S3 · private", s: "index, classic, status.json" }],
        { box: "serverless", label: "Serverless · no VPC", rows: [
          [{ id: "eb", i: "clock", c: "ops", t: "EventBridge", s: "Schedule rule, rate(15 minutes)" }, { id: "ad", i: "send", c: "ops", t: "API destination", s: "GitHub workflow_dispatch" }],
        ] },
        { heading: "Monitoring", tiles: [{ id: "cw", i: "pulse", c: "ops", t: "CloudWatch", s: "CloudFront · WAF · RUM · ALB · Bedrock" }] },
      ],
      security: [SEC_WAF("Free-plan ACL on CloudFront"), SEC_ACM("TLS certificate for CloudFront"), SEC_IAM("GitHub OIDC roles per workflow")],
      external: { label: "Outside AWS", rows: [
        [{ id: "gh", i: "branch", c: "ext", t: "GitHub Actions", s: "Status collector · Python, boto3" }],
        [{ id: "gr", i: "chart", c: "ext", t: "Grafana Cloud", s: "Synthetic checks" }, { id: "gs", i: "gateway", c: "ai", t: "gate.atla.in", s: "/v1/stats" }, { id: "cdn", i: "code", c: "ext", t: "jsDelivr", s: "three.js 0.186 for this page" }],
      ] },
      edges: [["u", "r53", "DNS", 1], ["r53", "cf", "alias", 1], ["cf", "s3", "origin", 1], ["eb", "ad", "fires"], ["ad", "gh", "dispatch", 0, "r"], ["gh", "s3", "status.json", 1, "r"], ["gh", "cw", "GetMetricData", 0, "l"], ["gh", "gr", "PromQL"], ["gh", "gs", "GET"]],
      delivery: STATIC_DELIVERY("pranavatla/obs.atla.in", "main", "deploy role", ["Stage index + classic", "s3 sync --delete", "CloudFront invalidation"], "deploy-frontend-aws.yml"),
      extra: "status.json is published separately by publish-status.yml, so page deploys never overwrite it.",
      watch: "Grafana synthetic check every 10 min · CloudWatch RUM · CloudFront and WAF metrics",
    },
    "games.atla.in": {
      summary: "Three browser games and a launcher on an S3 website endpoint in Mumbai, behind CloudFront and WAF. No VPC and no servers: the games run in the player's browser.",
      users: [{ id: "u", i: "users", c: "user", t: "Players", s: "Run the games locally" }],
      cloud: "AWS Cloud",
      rows: [
        [{ id: "r53", i: "dns", c: "net", t: "Route 53", s: "games.atla.in → CloudFront" }, { id: "cf", i: "cdn", c: "net", t: "CloudFront", s: "E1HCLV5K7MXCST · free plan" }, { id: "s3", i: "bucket", c: "storage", t: "S3 website", s: "ap-south-1 · launcher, Drop, Invaders, Break" }],
        { note: "No VPC, compute or database: every page is a static file." },
        { heading: "Monitoring", tiles: [{ id: "cw", i: "pulse", c: "ops", t: "CloudWatch", s: "CloudFront · WAF · RUM" }] },
      ],
      security: [SEC_WAF("Free-plan ACL on CloudFront"), SEC_ACM("TLS certificate for CloudFront"), SEC_IAM("OIDC role github-deploy-games-atla")],
      edges: [["u", "r53", "DNS", 1], ["r53", "cf", "alias", 1], ["cf", "s3", "origin", 1]],
      delivery: STATIC_DELIVERY("pranavatla/games.atla", "main", "github-deploy-games-atla", ["s3 cp launcher", "s3 sync each game", "CloudFront invalidation"], "deploy.yml"),
      watch: "Grafana synthetic check every 10 min · CloudWatch RUM · CloudFront and WAF metrics",
    },
    "aif.atla.in": {
      summary: "AWS AI Practitioner study guide on an S3 website endpoint in us-east-1, behind CloudFront without WAF. The repo documents a Lambda + API Gateway backend, but no page calls it, so it's drawn as not deployed.",
      users: [{ id: "u", i: "users", c: "user", t: "Learners", s: "Study pages + RUM" }],
      cloud: "AWS Cloud · us-east-1",
      rows: [
        [{ id: "r53", i: "dns", c: "net", t: "Route 53", s: "aif.atla.in → CloudFront" }, { id: "cf", i: "cdn", c: "net", t: "CloudFront", s: "E2A5DBVVXUZ6JO · pay-as-you-go" }, { id: "s3", i: "bucket", c: "storage", t: "S3 website", s: "Days 1–4, practice exams" }],
        { box: "planned", label: "Documented in the repo · not deployed", short: "Not deployed", rows: [
          [{ id: "apigw", i: "api", c: "ext", t: "API Gateway", s: "Planned" }, { id: "fn", i: "lambda", c: "ext", t: "Lambda", s: "Planned" }, { id: "ddb", i: "db", c: "ext", t: "DynamoDB", s: "Optional in the plan" }],
        ] },
        { heading: "Monitoring", tiles: [{ id: "cw", i: "pulse", c: "ops", t: "CloudWatch RUM", s: "us-east-1" }] },
      ],
      security: [SEC_ACM("TLS certificate for CloudFront"), SEC_IAM("OIDC role github-deploy-aif-c01")],
      edges: [["u", "r53", "DNS", 1], ["r53", "cf", "alias", 1], ["cf", "s3", "origin", 1], ["apigw", "fn"], ["fn", "ddb"]],
      delivery: STATIC_DELIVERY("pranavatla/aif-c01", "main", "github-deploy-aif-c01", ["s3 sync each day", "CloudFront invalidation"], "deploy.yml"),
      note: "No WAF on this distribution.",
      watch: "Grafana synthetic check every 10 min · CloudWatch RUM (us-east-1) · CloudFront metrics",
    },
  };

  const BOX_LABEL_CLS = { cloud: "b-cloud", vpc: "b-vpc", public: "b-public", private: "b-private", cluster: "b-cluster", group: "b-group", host: "b-cluster", serverless: "b-serverless", planned: "b-planned", external: "b-ext" };

  function renderArchitecture(domain, host) {
    const spec = ARCH[domain];
    host.replaceChildren();
    if (!spec) { host.append(el("p", "muted", "No architecture recorded for this site yet.")); return; }
    host.append(el("p", "arch-sum", spec.summary));

    const W = Math.max(330, Math.floor(host.clientWidth || 360));
    const wide = W >= 640;
    const TW = wide ? 132 : W >= 460 ? 96 : 78, TH = wide ? 80 : 70;
    const GAP = wide ? 14 : 8, PAD = wide ? 14 : 8, HEAD = 22, GUT = wide ? 26 : 18;

    // Deepest nesting decides where column 1 sits, so the first tile of every row lines up and the
    // main path runs straight down, like the reference diagrams.
    const depthOf = (rows, d) => Math.max(d, ...rows.filter((r) => r && r.box).map((r) => depthOf(r.rows, d + 1)));
    const cloudDepth = 1 + depthOf(spec.rows, 0);
    const extDepth = spec.external ? 1 : 0;
    const maxDepth = Math.max(cloudDepth, extDepth);
    const X0 = GUT + maxDepth * PAD;
    const colX = (k) => X0 + k * (TW + GAP);

    const mainIds = new Set(spec.edges.filter((e) => e[3]).flatMap((e) => [e[0], e[1]]));
    const rects = new Map();      // tile id -> {x, y, w, h, tile}
    const boxes = [];             // {x, y, w, h, label, kind}
    const texts = [];             // headings and notes {x, y, text, cls}
    let tiles = [];

    // Lays out a list of rows inside [left, right]; returns the bottom y.
    const layoutRows = (rows, left, right, y) => {
      rows.forEach((row) => {
        if (Array.isArray(row) || row.heading) {
          const list = Array.isArray(row) ? row : row.tiles;
          if (row.heading) { texts.push({ x: X0, y: y + 11, text: row.heading.toUpperCase(), cls: "a-head" }); y += 18; }
          let col = 0, rowY = y;
          // When a row that starts the main path wraps, later lines skip column 1 so the path stays clear
          const wrapCol = mainIds.has(list[0] && list[0].id) ? 1 : 0;
          list.forEach((t) => {
            const span = t.w || 1;
            if (t.col && col < t.col) col = t.col;   // keep column 1 clear for the main path
            if (col > 0 && colX(col + span) - GAP > right - PAD + 0.5) { col = wrapCol; rowY += TH + GAP; }
            const r = { x: colX(col), y: rowY, w: span * TW + (span - 1) * GAP, h: TH, tile: t };
            rects.set(t.id, r); tiles.push(r);
            col += span;
          });
          y = rowY + TH + GAP;
        } else if (row.note) {
          texts.push({ x: X0, y: y + 12, text: row.note, cls: "a-note", max: right - PAD - X0 });
          y += 26;
        } else if (row.box) {
          const top = y + 4, l = left + PAD, r = right - PAD;
          const end = layoutRows(row.rows, l, r, top + HEAD);
          boxes.push({ x: l, y: top, w: r - l, h: end - top + PAD - GAP + 6, label: row.label, short: row.short, kind: row.box });
          y = end + PAD - GAP + 6 + GAP + 2;
        }
      });
      return y;
    };

    let y = 6;
    // Users sit above the cloud
    spec.users.forEach((t, k) => { const r = { x: colX(k), y, w: TW, h: TH, tile: t }; rects.set(t.id, r); tiles.push(r); });
    y += TH + 26;
    const cloudTop = y;
    let inner = layoutRows(spec.rows, GUT, W - GUT, cloudTop + HEAD + 4);
    if (spec.security && spec.security.length) inner = layoutRows([{ heading: "Security & governance", tiles: spec.security }], GUT, W - GUT, inner + 2);
    boxes.unshift({ x: GUT, y: cloudTop, w: W - 2 * GUT, h: inner - cloudTop + PAD - GAP, label: spec.cloud, kind: "cloud" });
    y = inner + PAD - GAP + 22;
    if (spec.external) {
      const ext = spec.external;
      const end = layoutRows(ext.rows || [ext.tiles], GUT, W - GUT, y + HEAD + 4);
      boxes.push({ x: GUT, y, w: W - 2 * GUT, h: end - y + PAD - GAP, label: ext.label, kind: "external" });
      y = end + PAD - GAP + 8;
    }
    const H = y + 4;

    const NS = "http://www.w3.org/2000/svg";
    const mk = (tag, attrs, text) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (text != null) e.textContent = text; return e; };
    const fig = el("figure", "arch");
    const detail = el("p", "arch-detail", "Tap a service for its details.");
    const svg = mk("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": domain + " architecture: " + spec.summary });
    const uid = domain.replace(/\W/g, "");
    const defs = mk("defs");
    [["m", "a-ahm"], ["s", "a-ahs"]].forEach(([k, cls]) => {
      const m = mk("marker", { id: "ah" + k + uid, viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "6.5", markerHeight: "6.5", orient: "auto-start-reverse" });
      m.append(mk("path", { d: "M0 0 L10 5 L0 10 z", class: cls }));
      defs.append(m);
    });
    svg.append(defs);

    // Boundaries
    boxes.forEach((b) => svg.append(mk("rect", { x: b.x, y: b.y, width: b.w, height: b.h, rx: b.kind === "cloud" || b.kind === "cluster" || b.kind === "host" ? 10 : 6, class: "a-box " + BOX_LABEL_CLS[b.kind] })));

    // Arrows. Same-row neighbours join side to side; otherwise an elbow drops just above the target.
    // Edges marked "l" or "r" run down that side's gutter, like cable in a rack's side tray.
    const lanes = { l: 0, r: 0 };
    const sideSlots = new Map();
    spec.edges.forEach(([a, b, , , via]) => { if (!via) return; [a, b].forEach((id) => { const k = id + via; sideSlots.set(k, (sideSlots.get(k) || 0) + 1); }); });
    const sideUsed = new Map();
    const sideY = (id, via) => {
      const r = rects.get(id), k = id + via, n = sideSlots.get(k), j = sideUsed.get(k) || 0;
      sideUsed.set(k, j + 1);
      return r.y + r.h / 2 + (j - (n - 1) / 2) * 12;
    };
    const labels = [];
    spec.edges.forEach(([a, b, label, main, via]) => {
      const A = rects.get(a), B = rects.get(b);
      if (!A || !B) return;
      let d, lx, ly;
      if (via) {
        const lane = lanes[via]++;
        const gx = via === "l" ? GUT - 7 - lane * 6 : W - GUT + 7 + lane * 6;
        const ax = via === "l" ? A.x : A.x + A.w, bx = via === "l" ? B.x : B.x + B.w;
        const ay = sideY(a, via), by = sideY(b, via);
        d = `M${ax} ${ay} H${gx} V${by} H${bx}`;
        // Label near the arrow's start, so labels sharing a gutter never collide
        const tw = (label || "").length * 5.9 + 12;
        lx = gx; ly = ay + Math.sign(by - ay || 1) * (tw / 2 + 10);
      } else if (A.y + A.h <= B.y || B.y + B.h <= A.y) {
        const down = B.y > A.y;
        const ax = A.x + A.w / 2, bx = B.x + B.w / 2;
        const ay = down ? A.y + A.h : A.y, by = down ? B.y : B.y + B.h;
        if (Math.abs(ax - bx) < 2) { d = `M${ax} ${ay} V${by}`; lx = ax; ly = down ? ay + 10 : ay - 10; }   // just past the source, clear of box titles
        else {
          const ey = down ? by - 11 : by + 11;
          d = `M${ax} ${ay} V${ey} H${bx} V${by}`;
          lx = (ax + bx) / 2; ly = ey;
        }
      } else {
        const right = B.x > A.x;
        const ax = right ? A.x + A.w : A.x, bx = right ? B.x : B.x + B.w, yy = A.y + A.h / 2;
        d = `M${ax} ${yy} H${bx}`; lx = (ax + bx) / 2; ly = A.y - 9;   // above the gap, clear of the arrow and the box below
      }
      svg.append(mk("path", { d, class: "a-edge" + (main ? " main" : ""), "marker-end": `url(#ah${main ? "m" : "s"}${uid})` }));
      if (label) labels.push({ lx, ly, label, main, via });
    });

    // Boundary titles sit on the top border, cutting the line, as in the reference
    boxes.forEach((b) => {
      const room = (b.w - 40) / 6.6;
      if (b.label.length > room && b.short) b.label = b.short;
      if (b.label.length > room) b.label = b.label.slice(0, Math.max(4, Math.floor(room) - 1)) + "…";
      const tw = Math.min(b.w - 20, b.label.length * 6.6 + 14);
      const tx = b.x + b.w / 2;
      svg.append(mk("rect", { x: tx - tw / 2, y: b.y - 8, width: tw, height: 16, class: "a-cut" }));
      const t = mk("text", { x: tx, y: b.y + 4, "text-anchor": "middle", class: "a-blabel " + BOX_LABEL_CLS[b.kind] }, b.label);
      svg.append(t);
    });
    texts.forEach((t) => {
      let s = t.text;
      if (t.max) { const n = Math.floor(t.max / 6); if (s.length > n) s = s.slice(0, n - 1) + "…"; }
      svg.append(mk("text", { x: t.x, y: t.y, class: t.cls }, s));
    });

    // Service tiles
    const fit = (s, w, px) => { const n = Math.floor(w / px); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
    tiles.forEach(({ x, y, w, h, tile: t }) => {
      const g = mk("g", { class: "a-tile" + (t.c === "ext" ? " ext" : ""), tabindex: "0" });
      const full = [t.t, t.s].filter(Boolean).join(" · ");
      g.append(mk("title", {}, full));
      g.append(mk("rect", { x, y, width: w, height: h, rx: 8, class: "a-tbox" }));
      const isz = wide ? 30 : 26;
      const twoCol = (t.w || 1) > 1;
      const ix = twoCol ? x + 12 : x + w / 2 - isz / 2, iy = twoCol ? y + h / 2 - isz / 2 : y + 10;
      g.append(mk("rect", { x: ix, y: iy, width: isz, height: isz, rx: 6, fill: HUE[t.c] || HUE.ext }));
      const ic = mk("g", { transform: `translate(${ix + isz * 0.14} ${iy + isz * 0.14}) scale(${(isz * 0.72) / 24})`, class: "a-icon" });
      (ICONS[t.i] || ICONS.chip).forEach((p) => ic.append(mk("path", { d: p })));
      g.append(ic);
      if (twoCol) {
        const tx = ix + isz + 10, room = w - (tx - x) - 8;
        g.append(mk("text", { x: tx, y: y + h / 2 - 3, class: "a-ttl" }, fit(t.t, room, wide ? 7 : 6.4)));
        if (t.s) g.append(mk("text", { x: tx, y: y + h / 2 + 12, class: "a-sub" }, fit(t.s, room, 5.6)));
      } else {
        g.append(mk("text", { x: x + w / 2, y: iy + isz + 15, "text-anchor": "middle", class: "a-ttl" + (wide ? "" : " sm") }, fit(t.t, w - 6, wide ? 7 : 5.7)));
        if (t.s && wide) g.append(mk("text", { x: x + w / 2, y: iy + isz + 28, "text-anchor": "middle", class: "a-sub" }, fit(t.s, w - 10, 5.5)));
      }
      const show = () => { detail.textContent = full; svg.querySelectorAll(".a-tile.on").forEach((n) => n.classList.remove("on")); g.classList.add("on"); };
      g.addEventListener("click", show);
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); show(); } });
      svg.append(g);
    });

    // Arrow labels last, on pills
    labels.forEach(({ lx, ly, label, main, via }) => {
      const tw = label.length * 5.9 + 12;
      // Gutter labels run along their line, so they never spill onto the tiles beside the gutter
      const g = mk("g", via ? { transform: `rotate(-90 ${lx} ${ly})` } : {});
      const cx = via ? lx : Math.min(W - tw / 2 - 1, Math.max(tw / 2 + 1, lx));
      g.append(mk("rect", { x: cx - tw / 2, y: ly - 8.5, width: tw, height: 17, rx: 8.5, class: "a-pill" + (main ? " main" : "") }));
      g.append(mk("text", { x: cx, y: ly + 3.5, "text-anchor": "middle", class: "a-plabel" }, label));
      svg.append(g);
    });

    fig.append(svg);
    fig.append(detail);
    const cap = "Bright arrows are the main request path. Tap a service for its details. Drawn from the " + spec.delivery.repo + " repo." + (spec.note ? " " + spec.note : "");
    fig.append(el("figcaption", null, cap));
    host.append(fig);

    const del = el("section", "sec");
    const h3 = el("h3"); h3.append("Delivery · ");
    const a = el("a", null, spec.delivery.repo); a.href = "https://github.com/" + spec.delivery.repo; a.rel = "noopener"; a.target = "_blank";
    h3.append(a);
    del.append(h3);
    const lane = el("ol", "lane");
    spec.delivery.steps.forEach((s) => lane.append(el("li", null, s)));
    del.append(lane);
    del.append(el("p", "src", ".github/workflows/" + spec.delivery.file + (spec.extra ? " · " + spec.extra : "")));
    host.append(del);
    const w = el("section", "sec");
    w.append(el("h3", null, "Watched by"));
    w.append(el("p", "muted", spec.watch));
    host.append(w);
  }

  window.renderArchitecture = renderArchitecture;
  window.hasArchitecture = (domain) => Object.prototype.hasOwnProperty.call(ARCH, domain);
})();
