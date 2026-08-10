# Aegis Operations Dashboard

Next.js console for live incidents, evidence, agent plans, actions, and verification.

## Run

1. Start API + Postgres (from `aegis/`):

```bash
docker compose up -d
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

2. Start dashboard:

```bash
cd dashboard
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Config

`NEXT_PUBLIC_AEGIS_API_URL` defaults to `http://localhost:8000` (see `.env.local`).

## Features

- Live incident list with severity/status polling
- Simulate incident CTA (runs mock agent loop)
- Incident detail: timeline, evidence, hypotheses, plan, actions, before/after verification
- Approve button when status is `AWAITING_APPROVAL`
- API health indicator in the header
