# AtlaOps: AI-Powered Cloud Infrastructure Dashboard

AtlaOps is an interactive CloudOps portfolio product: a live operations-style dashboard with an embedded AI assistant (Ops Guru) powered by RAG context.

## Current Status (main branch)

Phase 1 + Phase 2 foundation is implemented:
- Live synthetic cloud metrics dashboard
- Service health table and latency trend chart
- Incident simulation controls (traffic spike, DB errors, recovery)
- Incident timeline and synthetic log stream
- Embedded AI assistant (`/generate/`) with KB retrieval + source citations

## Tech Stack

- FastAPI backend (`app1.py`)
- OpenAI API for chat generation
- ChromaDB persistent memory
- Vanilla HTML/CSS/JS frontend (`index.html`)
- Process entrypoint: `run.py`

## API Endpoints

- `GET /` -> AtlaOps dashboard UI
- `GET /health` -> service health and incident mode
- `POST /generate/` -> Ops Guru chat
- `GET /ops/metrics` -> synthetic infrastructure metrics + service statuses
- `GET /ops/logs?limit=20` -> synthetic logs
- `GET /ops/incidents` -> current incident + timeline
- `POST /ops/incidents/trigger` -> trigger `traffic_spike`, `db_errors`, `recovery`, `normal`
- `GET /ops/architecture` -> architecture node/flow data
- `GET /ops/kb/status` -> KB and memory collection counts

## Local Run

1. Install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Set env var:

```bash
export OPENAI_API_KEY=sk-...
```

3. Run:

```bash
python run.py
```

4. Open:

`http://localhost:8000`

## Ingest AtlaOps Knowledge Base (RAG)

Run ingestion before demoing chat grounding:

```bash
python ingest_atlaops_kb.py --reset
```

Then verify:
- `GET /ops/kb/status` should show `kb_chunks > 0`
- Ops Guru responses should include `Sources: ...`

## RAG Knowledge Base Seed

Starter docs for grounding are in:
- `docs/atlaops-kb/architecture.md`
- `docs/atlaops-kb/incidents.md`
- `docs/atlaops-kb/projects.md`

These documents should be ingested into the vector store before production demos.

## Next Build Targets

- Real RAG chunking + citation output in chat responses
- Architecture diagram visualization (interactive)
- Incident replay panel with RCA summaries
- IaC + CI/CD pipeline assets for AWS deployment path
