from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import math
import os
import shutil
import time
import re

try:
    import chromadb
except Exception:
    chromadb = None

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from mangum import Mangum
from openai import APIError, AuthenticationError, OpenAI, RateLimitError
from pydantic import BaseModel


app = FastAPI(title="AtlaOps AI Agent", version="4.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
EMBEDDING_MODEL = "text-embedding-3-small"

PROJECT_ROOT = Path(__file__).resolve().parent
CHROMA_PATH = Path(os.environ.get("CHROMA_PATH", "/tmp/atlaops_chroma_db"))
INDEX_HTML = PROJECT_ROOT / "index.html"
KB_SOURCE_DIRS = [PROJECT_ROOT / "docs" / "atlaops-kb", PROJECT_ROOT / "knowledge_base"]

request_log = defaultdict(list)
RATE_LIMIT = 20
WINDOW = 60

ALLOWED_INCIDENTS = {"normal", "traffic_spike", "db_errors", "recovery"}

SYSTEM_PROMPT = (
    "You are AtlaOps Guru, an AI cloud operations assistant built by Sai Pranav Atla. "
    "Give concise, technically precise answers. "
    "When knowledge-base context is provided, ground your answer in it and reference evidence briefly."
)

ops_state = {
    "incident": "normal",
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "timeline": [
        {
            "time": datetime.now(timezone.utc).isoformat(),
            "event": "System initialized in healthy state.",
        }
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def embed_texts(texts: list[str]) -> list[list[float]]:
    if openai_client is None:
        return []
    try:
        response = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
        return [item.embedding for item in response.data]
    except Exception:
        return []


def init_collections():
    if chromadb is None:
        return None, None

    try:
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        user_memory = chroma_client.get_or_create_collection(name="user_memory")
        kb_docs = chroma_client.get_or_create_collection(name="atlaops_kb")
        return user_memory, kb_docs
    except Exception as exc:
        backup_dir = CHROMA_PATH.with_name(f"{CHROMA_PATH.name}_legacy_{int(time.time())}")
        if CHROMA_PATH.exists():
            shutil.move(str(CHROMA_PATH), str(backup_dir))
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        user_memory = chroma_client.get_or_create_collection(name="user_memory")
        kb_docs = chroma_client.get_or_create_collection(name="atlaops_kb")
        print(f"ChromaDB reset after init failure: {exc}. Backup: {backup_dir}")
        return user_memory, kb_docs


user_collection, kb_collection = init_collections()


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not normalized:
        return []

    chunks = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = max(0, end - overlap)
    return chunks


def load_file_kb_chunks() -> list[dict]:
    chunks = []
    for kb_dir in KB_SOURCE_DIRS:
        if not kb_dir.exists():
            continue
        for path in sorted(kb_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
                continue
            try:
                rel = path.relative_to(PROJECT_ROOT).as_posix()
                for idx, chunk in enumerate(chunk_text(path.read_text(encoding="utf-8"))):
                    chunks.append({"text": chunk, "source": rel, "chunk_index": idx})
            except Exception:
                continue
    return chunks


FILE_KB_CHUNKS = load_file_kb_chunks()
FILE_KB_EMBEDDINGS: list[list[float]] | None = None


def tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text.lower())}


def cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def retrieve_file_kb_context(query: str, top_k: int = 4):
    if not FILE_KB_CHUNKS:
        return "", []

    global FILE_KB_EMBEDDINGS

    query_embedding = embed_texts([query])
    if query_embedding:
        if FILE_KB_EMBEDDINGS is None:
            FILE_KB_EMBEDDINGS = embed_texts([item["text"] for item in FILE_KB_CHUNKS])
        if FILE_KB_EMBEDDINGS:
            scored = [
                (cosine_similarity(query_embedding[0], embedding), item)
                for item, embedding in zip(FILE_KB_CHUNKS, FILE_KB_EMBEDDINGS)
            ]
        else:
            scored = []
    else:
        query_tokens = tokenize(query)
        scored = [
            (len(query_tokens & tokenize(item["text"])), item)
            for item in FILE_KB_CHUNKS
        ]

    top = [item for score, item in sorted(scored, key=lambda row: row[0], reverse=True)[:top_k] if score > 0]
    if not top:
        top = FILE_KB_CHUNKS[:top_k]

    contexts = [
        f"[{item['source']}#chunk-{item['chunk_index']}] {item['text']}"
        for item in top
    ]
    sources = [
        {"source": item["source"], "chunk": item["chunk_index"]}
        for item in top
    ]
    return "\n\n".join(contexts), sources


def reset_user_collection():
    global user_collection

    if chromadb is None:
        user_collection = None
        return

    client_local = chromadb.PersistentClient(path=str(CHROMA_PATH))
    try:
        client_local.delete_collection("user_memory")
    except Exception:
        pass
    user_collection = client_local.get_or_create_collection(name="user_memory")


class PromptRequest(BaseModel):
    prompt: str


class IncidentRequest(BaseModel):
    incident_type: str


def push_timeline(event: str) -> None:
    ops_state["timeline"].insert(0, {"time": utc_now(), "event": event})
    ops_state["timeline"] = ops_state["timeline"][:30]
    ops_state["updated_at"] = utc_now()


def get_ai_response(full_prompt: str) -> str:
    if openai_client is None:
        return "AI service configuration issue."

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": full_prompt},
            ],
            temperature=0.4,
            max_tokens=500,
        )
        return response.choices[0].message.content
    except RateLimitError:
        return "LLM rate limit reached. Please retry in a few seconds."
    except AuthenticationError:
        return "AI service authentication failed."
    except APIError:
        return "AI service currently unavailable."
    except Exception:
        return "Unexpected AI service error."


def generate_metrics() -> dict:
    t = time.time() / 6.0
    incident = ops_state["incident"]

    cpu = 42 + 8 * math.sin(t)
    memory = 58 + 6 * math.cos(t / 2)
    latency = 120 + 20 * math.sin(t / 1.3)
    error_rate = 0.4 + 0.2 * abs(math.sin(t / 1.1))
    pods = 6 + int(abs(math.sin(t / 1.8)) * 2)
    rps = 190 + int(abs(math.sin(t)) * 35)

    if incident == "traffic_spike":
        cpu += 35
        latency += 120
        error_rate += 1.4
        pods += 5
        rps += 340
    elif incident == "db_errors":
        cpu += 12
        memory += 10
        latency += 85
        error_rate += 3.2
    elif incident == "recovery":
        cpu -= 8
        latency -= 20
        error_rate -= 0.2

    cpu = max(5, min(99, round(cpu, 1)))
    memory = max(10, min(99, round(memory, 1)))
    latency = max(40, round(latency, 1))
    error_rate = max(0.0, round(error_rate, 2))

    checkout_status = "degraded" if incident == "db_errors" else "healthy"
    api_status = "degraded" if incident in {"traffic_spike", "db_errors"} else "healthy"

    services = [
        {"name": "api-gateway", "status": api_status, "latency_ms": round(latency * 0.9, 1)},
        {"name": "orders-service", "status": checkout_status, "latency_ms": latency},
        {"name": "payments-worker", "status": checkout_status, "latency_ms": round(latency * 1.1, 1)},
        {"name": "ops-guru-rag", "status": "healthy", "latency_ms": round(latency * 0.75, 1)},
    ]

    return {
        "timestamp": utc_now(),
        "incident": incident,
        "metrics": {
            "cpu_percent": cpu,
            "memory_percent": memory,
            "latency_p95_ms": latency,
            "error_rate_percent": error_rate,
            "pod_count": pods,
            "requests_per_min": rps,
        },
        "services": services,
    }


def generate_logs(limit: int) -> list[dict]:
    incident = ops_state["incident"]
    base = [
        "INFO api-gateway request completed route=/health status=200",
        "INFO orders-service cache hit ratio=0.93",
        "INFO payments-worker batch settled count=21",
        "INFO ops-guru-rag context chunks=4 retrieval_ms=41",
    ]

    if incident == "traffic_spike":
        base.extend(
            [
                "WARN autoscaler scale_out pods=+3 reason=cpu_above_threshold",
                "WARN api-gateway latency elevated p95=290ms",
                "ALERT cloudwatch HighRequestRate triggered",
            ]
        )
    elif incident == "db_errors":
        base.extend(
            [
                "ERROR orders-db timeout query=SELECT * FROM orders",
                "ERROR payments-worker retry exhausted payment_id=py_8172",
                "ALERT cloudwatch DatabaseErrorRate triggered",
            ]
        )
    elif incident == "recovery":
        base.extend(
            [
                "INFO incident-automation remediation playbook completed",
                "INFO api-gateway latency recovered p95=128ms",
                "RESOLVED cloudwatch alarms back to normal",
            ]
        )

    logs = []
    for i in range(limit):
        entry = base[i % len(base)]
        logs.append({"time": utc_now(), "line": entry})
    return logs


def build_ops_context() -> str:
    metrics_payload = generate_metrics()
    metrics = metrics_payload["metrics"]
    recent_logs = generate_logs(4)
    recent_events = ops_state["timeline"][:3]

    log_lines = " | ".join(log["line"] for log in recent_logs)
    timeline_lines = " | ".join(event["event"] for event in recent_events)

    return (
        f"Incident mode: {ops_state['incident']}. "
        f"CPU={metrics['cpu_percent']}%, Memory={metrics['memory_percent']}%, "
        f"P95 Latency={metrics['latency_p95_ms']}ms, Errors={metrics['error_rate_percent']}%, "
        f"Pods={metrics['pod_count']}, RPM={metrics['requests_per_min']}. "
        f"Recent timeline: {timeline_lines}. "
        f"Recent logs: {log_lines}."
    )


def retrieve_kb_context(query: str, top_k: int = 4):
    if kb_collection is None or kb_collection.count() == 0:
        return retrieve_file_kb_context(query, top_k=top_k)

    try:
        query_embedding = embed_texts([query])
        if not query_embedding:
            return "", []
        results = kb_collection.query(query_embeddings=query_embedding, n_results=top_k)
    except Exception:
        return retrieve_file_kb_context(query, top_k=top_k)
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    contexts = []
    sources = []

    for idx, doc in enumerate(documents):
        meta = metadatas[idx] if idx < len(metadatas) and metadatas[idx] else {}
        source = meta.get("source", "unknown")
        chunk_index = meta.get("chunk_index", "?")
        contexts.append(f"[{source}#chunk-{chunk_index}] {doc}")
        sources.append({"source": source, "chunk": chunk_index})

    context_block = "\n\n".join(contexts)
    dedup = []
    seen = set()
    for source in sources:
        key = (source["source"], str(source["chunk"]))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(source)

    return context_block, dedup


def retrieve_memory_context(query: str, top_k: int = 2) -> str:
    if user_collection is None or user_collection.count() == 0:
        return ""
    try:
        query_embedding = embed_texts([query])
        if not query_embedding:
            return ""
        results = user_collection.query(query_embeddings=query_embedding, n_results=top_k)
    except Exception:
        return ""
    documents = results.get("documents", [[]])[0]
    if not documents:
        return ""
    return "\n".join(documents)


@app.get("/")
def root():
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML)
    return {"message": "AtlaOps backend is running."}


@app.get("/health")
def health():
    chroma_kb_count = kb_collection.count() if kb_collection is not None else 0
    return {
        "status": "ok",
        "backend": "openai" if OPENAI_API_KEY else "none",
        "rate_limit": f"{RATE_LIMIT} req/{WINDOW}s",
        "version": "4.1.0",
        "incident": ops_state["incident"],
        "kb_chunks": chroma_kb_count or len(FILE_KB_CHUNKS),
    }


@app.get("/ops/metrics")
def ops_metrics():
    return generate_metrics()


@app.get("/ops/logs")
def ops_logs(limit: int = Query(default=20, ge=5, le=100)):
    return {"incident": ops_state["incident"], "logs": generate_logs(limit)}


@app.get("/ops/incidents")
def ops_incidents():
    return {
        "incident": ops_state["incident"],
        "updated_at": ops_state["updated_at"],
        "timeline": ops_state["timeline"],
    }


@app.post("/ops/incidents/trigger")
def trigger_incident(payload: IncidentRequest):
    incident_type = payload.incident_type.strip().lower()
    if incident_type not in ALLOWED_INCIDENTS:
        raise HTTPException(status_code=400, detail="Unsupported incident type")

    ops_state["incident"] = incident_type
    if incident_type == "traffic_spike":
        push_timeline("Traffic spike simulation started. Autoscaling initiated.")
    elif incident_type == "db_errors":
        push_timeline("Database error burst simulated. Checkout degradation detected.")
    elif incident_type == "recovery":
        push_timeline("Recovery workflow simulated. Services stabilizing.")
    else:
        push_timeline("System returned to normal baseline.")

    return {"ok": True, "incident": ops_state["incident"], "updated_at": ops_state["updated_at"]}


@app.get("/ops/architecture")
def ops_architecture():
    return {
        "nodes": [
            "Route53",
            "CloudFront",
            "S3 Frontend",
            "API Gateway",
            "Lambda AtlaOps API",
            "OpenAI LLM",
            "Vector Store",
            "CloudWatch",
        ],
        "edges": [
            ["Route53", "CloudFront"],
            ["CloudFront", "S3 Frontend"],
            ["CloudFront", "API Gateway"],
            ["API Gateway", "Lambda AtlaOps API"],
            ["Lambda AtlaOps API", "OpenAI LLM"],
            ["Lambda AtlaOps API", "Vector Store"],
            ["Lambda AtlaOps API", "CloudWatch"],
        ],
    }


@app.get("/ops/kb/status")
def kb_status():
    chroma_kb_count = kb_collection.count() if kb_collection is not None else 0
    return {
        "kb_chunks": chroma_kb_count or len(FILE_KB_CHUNKS),
        "file_kb_chunks": len(FILE_KB_CHUNKS),
        "memory_chunks": user_collection.count() if user_collection is not None else 0,
    }


@app.get("/ops/incidents/rca")
def incident_rca():
    incident = ops_state["incident"]
    metrics = generate_metrics()["metrics"]
    recent_logs = [entry["line"] for entry in generate_logs(8)]
    recent_events = [entry["event"] for entry in ops_state["timeline"][:4]]

    if incident == "traffic_spike":
        summary = "Traffic surge caused latency amplification and autoscaling pressure."
        likely_root_cause = "Request rate exceeded baseline, saturating API gateway and service pods."
        mitigation = [
            "Scale out stateless services and verify autoscaler thresholds.",
            "Apply temporary rate limiting for abusive clients.",
            "Tune cache and edge TTL for high-read paths.",
        ]
    elif incident == "db_errors":
        summary = "Checkout path degradation driven by database timeouts."
        likely_root_cause = "Orders database query latency and retries increased error propagation."
        mitigation = [
            "Investigate slow queries and connection pool saturation.",
            "Enable circuit-breaker behavior for failing DB dependencies.",
            "Shift read-heavy paths to cache and validate retry/backoff config.",
        ]
    elif incident == "recovery":
        summary = "System is in recovery mode after mitigation workflow."
        likely_root_cause = "Prior incident signals are stabilizing after remediation actions."
        mitigation = [
            "Keep elevated monitoring until latency and error trends fully normalize.",
            "Run post-incident validation checks on dependent services.",
            "Document timeline and finalize postmortem actions.",
        ]
    else:
        summary = "No active incident detected; platform is operating at baseline."
        likely_root_cause = "N/A"
        mitigation = [
            "Maintain baseline observability and alert hygiene.",
            "Run periodic failure drills to validate runbooks.",
            "Review capacity thresholds before peak traffic windows.",
        ]

    return {
        "incident": incident,
        "generated_at": utc_now(),
        "summary": summary,
        "likely_root_cause": likely_root_cause,
        "signals": {
            "cpu_percent": metrics["cpu_percent"],
            "memory_percent": metrics["memory_percent"],
            "latency_p95_ms": metrics["latency_p95_ms"],
            "error_rate_percent": metrics["error_rate_percent"],
            "pod_count": metrics["pod_count"],
            "requests_per_min": metrics["requests_per_min"],
        },
        "recent_events": recent_events,
        "recent_logs": recent_logs,
        "mitigation_plan": mitigation,
    }


@app.post("/generate/")
async def generate_text(request: Request, prompt_req: PromptRequest):
    try:
        if not OPENAI_API_KEY:
            return {
                "response": "OPENAI_API_KEY is not configured in this running server process.",
                "sources": [],
                "incident": ops_state["incident"],
            }

        client_ip = request.client.host if request.client else "unknown"
        current_time = time.time()

        request_log[client_ip] = [t for t in request_log[client_ip] if current_time - t < WINDOW]
        if len(request_log[client_ip]) >= RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
        request_log[client_ip].append(current_time)

        user_message = prompt_req.prompt.strip()
        if not user_message:
            raise HTTPException(status_code=400, detail="Prompt is required.")

        ops_context = build_ops_context()
        kb_context, sources = retrieve_kb_context(user_message, top_k=4)
        memory_context = retrieve_memory_context(user_message, top_k=2)

        full_prompt = (
            f"Current ops state:\n{ops_context}\n\n"
            f"Knowledge base context:\n{kb_context or 'No KB chunks found.'}\n\n"
            f"Conversation memory:\n{memory_context or 'No prior memory found.'}\n\n"
            f"User question: {user_message}\n\n"
            "Instructions: use the context above when relevant, be explicit about incident signals, "
            "and avoid claims not supported by the provided context."
        )

        ai_response = get_ai_response(full_prompt)

        memory_doc = f"User asked: {user_message}. AtlaOps Guru replied: {ai_response}"
        memory_embeddings = embed_texts([memory_doc])
        if user_collection is not None and memory_embeddings:
            try:
                user_collection.add(
                    documents=[memory_doc],
                    embeddings=memory_embeddings,
                    metadatas=[{"source": "conversation", "time": utc_now()}],
                    ids=[f"conv_{time.time()}"],
                )
            except Exception as exc:
                if "dimensionality" in str(exc).lower():
                    reset_user_collection()
                    if user_collection is not None:
                        user_collection.add(
                            documents=[memory_doc],
                            embeddings=memory_embeddings,
                            metadatas=[{"source": "conversation", "time": utc_now()}],
                            ids=[f"conv_{time.time()}"],
                        )
                else:
                    raise

        return {
            "response": ai_response,
            "sources": sources,
            "incident": ops_state["incident"],
        }
    except HTTPException:
        raise
    except Exception as exc:
        return {
            "response": f"Ops Guru backend error: {type(exc).__name__}: {exc}",
            "sources": [],
            "incident": ops_state["incident"],
        }


handler = Mangum(app)
