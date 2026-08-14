# Aegis — Autonomous AI Operations Agent

Aegis is an **agentic** cloud operations system. It receives an incident, investigates with tools, performs differential diagnosis, proposes a risk-tiered remediation, executes allowlisted actions (or waits for human approval), verifies recovery, and stores a full timeline in PostgreSQL.

Tools use the **same names** for mock demos and live AWS (`AEGIS_TOOL_BACKEND=mock|aws`). Live mode talks to your existing EC2 + CloudWatch via access keys and SSM.

## Why this is agentic (not a chatbot)

```
Event → Observe → Investigate → Reason → Choose tool → Execute
      → Observe result → Re-evaluate → Fix / escalate / ask human
```

Agents decide the next investigation step from current evidence (e.g. check MySQL before restarting Node), and a coded safety policy gates every write action.

## Stack
- **CrewAI** specialized multi-agent workflow (with deterministic fallback when no OpenAI key)
- **FastAPI** control plane
- **PostgreSQL** (Docker) for incidents, evidence, plans, actions, verification, audit
- **Next.js** operations dashboard
- **Pydantic** structured schemas + coded safety policy

## Specialized agents (CrewAI mode)

| Agent | Responsibility |
|-------|----------------|
| Incident Manager | What is happening? Set investigation priorities |
| Monitoring | CloudWatch / host metrics / HTTP health |
| Log Analyst | Application + PM2 log patterns |
| Infrastructure | EC2, nginx, processes, PM2 |
| Database | MySQL health / rule-out |
| Diagnosis | Scored hypotheses + root cause |
| Decision / Planner | Lowest-risk allowlisted remediation |
| Recovery + Verification | Python-enforced execute → verify (not free-form LLM writes) |

## Tools (mock or AWS)

Read: `get_cloudwatch_alarm`, `get_cloudwatch_metric`, `get_cpu_usage`, `get_memory_usage`, `get_disk_usage`, `get_swap_usage`, `get_system_metrics`, `get_processes`, `get_process_memory`, `query_logs`, `get_pm2_status`, `get_pm2_logs`, `get_mysql_status`, `get_nginx_status`, `get_ec2_status`, `health_check`

Write (policy-gated): `restart_pm2_process`, `clear_temp_files`, `rotate_logs`, `restart_mysql`, `scale_ec2`, `change_configuration`

| Tool area | Mock | AWS backend |
|-----------|------|-------------|
| Alarms / metrics | in-memory | CloudWatch |
| EC2 status | fixture | `DescribeInstances` |
| Host / PM2 / logs | fixture | SSM `AWS-RunShellScript` |
| Health check | fixture | `AEGIS_HEALTHCHECK_URL` |
| MySQL / ASG writes | mock scenarios | phase-1 stubbed (not live yet) |

## Safety model (production-minded)

| Tier | Examples | Behavior |
|------|----------|----------|
| Low | restart PM2, clear temp files, rotate logs | Auto-execute |
| Medium | restart MySQL, change config, scale EC2 | Human approval required |
| Critical | DROP DATABASE, delete data, terminate EC2, modify IAM | Never auto-execute |

Also: action allowlists, parameter allowlists, max actions per incident, no arbitrary shell from the LLM.

## Quick start

### 1) Start MySQL (XAMPP)
Open **XAMPP Manager** and start **MySQL**, then create the app database once:

```bash
/Applications/XAMPP/xamppfiles/bin/mysql -u root -e "CREATE DATABASE IF NOT EXISTS aegis CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

`DATABASE_URL` defaults to `mysql+pymysql://root:@127.0.0.1:3306/aegis` (empty password).  
Optional Postgres: `docker compose up -d` and set `DATABASE_URL=postgresql+psycopg://aegis:aegis@localhost:5432/aegis`.

### 2) Create virtualenv and install
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 3) Configure agents + optional AWS
In `.env`:
- Leave `OPENAI_API_KEY` empty to run **deterministic** agent mode
- Or set `OPENAI_API_KEY=sk-...` and `AEGIS_AGENT_MODE=auto` to use **CrewAI + OpenAI**
- Keep `AEGIS_TOOL_BACKEND=mock` for local demos
- For live AWS, set:

```bash
AEGIS_TOOL_BACKEND=aws
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
AEGIS_EC2_INSTANCE_ID=i-xxxxxxxx
AEGIS_CW_ALARM_NAME=your-existing-alarm
AEGIS_HEALTHCHECK_URL=http://YOUR_HOST/health   # optional
```

**EC2 prerequisites:** SSM Agent online (Systems Manager → Managed instances), instance role allowing SSM, PM2 on the host, CloudWatch alarm name matching `.env`.

**IAM (local access keys) — least privilege sketch:**
- `cloudwatch:DescribeAlarms`, `cloudwatch:GetMetricStatistics`
- `ec2:DescribeInstances`, `ec2:DescribeInstanceStatus`
- `ssm:SendCommand`, `ssm:GetCommandInvocation`, `ssm:DescribeInstanceInformation`

Never commit `.env`. Prefer a dedicated IAM user (not AdministratorAccess).

### 4) Run API
```bash
# If venv scripts have a broken shebang path, prefer:
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

### 5) Simulate (mock) or live AWS
```bash
# Low-risk mock path → auto recover
curl -s -X POST http://localhost:8000/incidents/simulate \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"api_memory_pressure","service":"production-api","severity":"HIGH"}' | python3 -m json.tool

# Medium-risk mock path → AWAITING_APPROVAL, then approve to resume
curl -s -X POST http://localhost:8000/incidents/simulate \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"mysql_restart_required","service":"production-api","severity":"CRITICAL"}' | python3 -m json.tool

curl -s -X POST http://localhost:8000/incidents/<id>/approve \
  -H 'Content-Type: application/json' \
  -d '{"approved_by":"operator"}' | python3 -m json.tool

# Live AWS (requires AEGIS_TOOL_BACKEND=aws + credentials)
curl -s -X POST http://localhost:8000/incidents/live \
  -H 'Content-Type: application/json' \
  -d '{"service":"production-api","severity":"HIGH"}' | python3 -m json.tool
```

### 6) Dashboard
```bash
cd dashboard
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Use mock simulate buttons or **Run against live AWS**.

## Scenarios

1. **`api_memory_pressure`** (mock) — Host memory high; MySQL looks large but healthy; Node/PM2 `api` unhealthy → auto `restart_pm2_process` → verify → `RECOVERED`
2. **`mysql_restart_required`** (mock) — MySQL saturated → plan `restart_mysql` → `AWAITING_APPROVAL` → approve → `RECOVERED` (or reject → `ESCALATED`)
3. **`live_aws`** — Real CloudWatch/EC2/SSM investigation; low-risk PM2 restart via SSM when policy allows

## API
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | App + DB + agent mode + tool backend |
| POST | `/incidents/simulate` | Run end-to-end **mock** incident |
| POST | `/incidents/live` | Run against **real AWS** (no mock bootstrap) |
| POST | `/incidents/investigate` | Free-text issue → live AWS investigation (PM2 `websites` / `node-server`) |
| GET | `/incidents` | List incidents |
| GET | `/incidents/{id}` | Full timeline |
| POST | `/incidents/{id}/approve` | Approve medium-risk plan and resume execute/verify |
| POST | `/incidents/{id}/reject` | Reject plan and escalate |

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
│   ├── tools/           # Mock + AWS backends (CloudWatch/EC2/SSM)
│   ├── policies/        # Allowlist + risk tiers + approval rules
│   ├── services/        # State machine, orchestrator, remediation
│   ├── models/          # SQLAlchemy + Pydantic
│   └── database/        # Engine/session
├── dashboard/           # Next.js operations console
├── runbooks/
├── tests/
└── docker-compose.yml
```

## Next phases
- EventBridge alarm → auto-create live incident
- Enable MySQL/ASG remediations on AWS behind approval
- Runbook RAG + evaluation harness
