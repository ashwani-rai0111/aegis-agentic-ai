# Aegis — Autonomous AI Operations Agent (MVP)

Aegis is an **agentic** cloud operations prototype. It receives an incident, investigates with tools, decides a root cause, proposes a safe remediation, executes an allowlisted action, verifies recovery, and stores a full timeline in PostgreSQL.

This MVP uses **local mock AWS/SSM/PM2 tools** first. The same tool names can later be backed by real AWS APIs.

## Stack
- **CrewAI** multi-agent workflow (with deterministic fallback when no OpenAI key)
- **FastAPI** control plane
- **PostgreSQL** (Docker) for incidents, evidence, plans, actions, verification, audit
- **Pydantic** structured schemas + coded safety policy

## Quick start

### 1) Start Postgres
```bash
cd aegis
docker compose up -d
```

### 2) Create virtualenv and install
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 3) Configure agents
In `.env`:
- Leave `OPENAI_API_KEY` empty to run **deterministic** agent mode (no LLM cost; still full observe→act→verify loop)
- Or set `OPENAI_API_KEY=sk-...` and `AEGIS_AGENT_MODE=auto` to use **CrewAI + OpenAI**

### 4) Run API
```bash
uvicorn app.main:app --reload --port 8000
```

### 5) Simulate an incident
```bash
curl -s -X POST http://localhost:8000/incidents/simulate \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"api_memory_pressure","service":"production-api","severity":"HIGH"}' | python3 -m json.tool
```

Open interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### 6) Start the operations dashboard
```bash
cd dashboard
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) for the live incident console (list, simulate, timeline, evidence, approvals, verification).

## What the simulation does
1. Creates a CloudWatch-style latency/memory alarm (mock)
2. Agents gather metrics, PM2 status, and logs
3. RCA selects the most likely root cause
4. Planner proposes `restart_pm2_process(process_name=api)`
5. Safety policy allowlists and auto-approves this low-risk action
6. Action agent restarts the mock PM2 process
7. Verification confirms latency/memory/alarm recovery
8. Incident status becomes `RECOVERED` with a persisted timeline

## API
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | App + DB + agent mode |
| POST | `/incidents/simulate` | Run end-to-end mock incident |
| GET | `/incidents` | List incidents |
| GET | `/incidents/{id}` | Full timeline |
| POST | `/incidents/{id}/approve` | Approve high-risk plans (MVP hook) |

## Tests
```bash
# unit tests (no Postgres required)
pytest tests/test_safety.py tests/test_state_machine.py -q

# e2e (requires Docker Postgres)
pytest tests/test_simulate_e2e.py -q
```

## Project layout
```
aegis/
├── app/
│   ├── agents/          # CrewAI crew + deterministic fallback
│   ├── api/             # FastAPI routes
│   ├── tools/           # Mock CloudWatch/SSM/PM2 tools
│   ├── policies/        # Allowlist + approval rules
│   ├── services/        # Incident state machine + orchestrator
│   ├── models/          # SQLAlchemy + Pydantic
│   └── database/        # Engine/session
├── dashboard/           # Next.js operations console
├── runbooks/
├── tests/
└── docker-compose.yml
```

## Safety model
- Read-only tools are always allowed
- Write tools must be allowlisted
- Max 1 action per incident in MVP
- No arbitrary shell from the LLM
- High-risk actions require human approval (blocked/escalated unless approved)

## Next phases
- Swap mock tools for real CloudWatch + SSM
- Runbook RAG
- More remediation actions + evaluation harness
