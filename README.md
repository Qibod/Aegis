# Aegis — Intelligent GRC Platform

AI-powered Governance, Risk & Compliance platform for modern financial institutions.

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 18 + TypeScript + Vite + Zustand |
| Backend | FastAPI + SQLAlchemy (async) + PostgreSQL + pgvector |
| AI | Anthropic Claude (sonnet-4-5) |
| Queue | Celery + Redis |
| Infra | Docker Compose (dev) · Vercel (frontend) · Railway (backend) |

## Local Development

### Prerequisites
- Docker & Docker Compose
- Node 20+
- An Anthropic API key

### Backend

```bash
cd aegis-backend
cp .env.example .env          # fill in ANTHROPIC_API_KEY, JWT_SECRET_KEY, SECRET_KEY
docker compose up -d          # starts api, db, redis, worker, beat
```

API runs at `http://localhost:8000` · Docs at `http://localhost:8000/docs`

### Frontend

```bash
cd aegis-frontend
npm install
npm run dev                   # http://localhost:3000
```

## Deployment

### Backend → Railway

1. Create a Railway project and add a **PostgreSQL** plugin and a **Redis** plugin
2. Connect this GitHub repo, set **Root Directory** to `aegis-backend`
3. Add environment variables (see `aegis-backend/.env.example`):
   - `APP_ENV=production`
   - `SECRET_KEY=<strong-random-string>`
   - `JWT_SECRET_KEY=<strong-random-string>`
   - `ANTHROPIC_API_KEY=sk-ant-...`
   - `DATABASE_URL=<railway-postgres-url>`  (auto-set by plugin)
   - `REDIS_URL=<railway-redis-url>`        (auto-set by plugin)
   - `ALLOWED_ORIGINS=https://your-app.vercel.app`
4. Railway auto-detects the `Dockerfile` and `railway.toml`

### Frontend → Vercel

1. Import this GitHub repo into Vercel
2. Set **Root Directory** to `aegis-frontend`
3. Framework preset: **Vite**
4. Add environment variable:
   - `VITE_API_BASE_URL=https://your-backend.up.railway.app/api/v1`
5. Deploy — auto-deploys on every push to `main`

## Features

- 🛡️ **Risk Register** — AI-seeded risk catalogue with severity scoring
- 🗺️ **Risk Terrain** — Interactive 3D terrain map (Three.js)
- 🎛️ **Control Canvas** — Living risk-control relationship graph
- 📡 **Risk Radar** — Real-time threat intelligence feed
- ⚡ **Control Pulse** — Continuous control health monitoring
- 🕰️ **Time Machine** — Historical GRC snapshots + scenario simulation
- 📋 **Regulatory Change Agent** — AI-tracked regulatory pipeline
- 📊 **AI Audit Report** — 4-stage Claude pipeline (IIA-standard)
- 🤖 **AI Co-Auditor** — Three-panel audit workspace (anomaly · workpaper · interview)
