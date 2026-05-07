# Aegis GRC Platform — Backend

Intelligent GRC and audit platform backend built with FastAPI, PostgreSQL, and Claude AI.

## Quick start (Docker — recommended)

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY at minimum

# 2. Start all services
docker compose up -d

# 3. API is live at http://localhost:8000
# 4. Interactive docs at http://localhost:8000/docs
# 5. Celery monitoring at http://localhost:5555
```

## Manual setup (without Docker)

### Prerequisites
- Python 3.12+
- PostgreSQL 16 with pgvector extension
- Redis 7

### Install

```bash
# Create virtualenv
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your values
```

### Database setup

```bash
# Create database
createdb aegis

# Enable pgvector (run in psql)
psql aegis -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql aegis -c "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"

# Run migrations
alembic upgrade head

# Or in development (auto-creates tables on startup):
# Set DEBUG=true in .env — tables are created automatically
```

### Run the API

```bash
# Development (with hot reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Run background workers

```bash
# Celery worker (in a separate terminal)
celery -A app.workers.tasks.celery_app worker --loglevel=info

# Celery beat scheduler (in another terminal)
celery -A app.workers.tasks.celery_app beat --loglevel=info
```

## Project structure

```
aegis-backend/
├── app/
│   ├── main.py              # FastAPI app factory + router registration
│   ├── config.py            # Settings from environment variables
│   ├── database.py          # Async SQLAlchemy engine + session
│   ├── models/
│   │   └── __init__.py      # All ORM models (12 tables)
│   ├── schemas/
│   │   └── __init__.py      # All Pydantic request/response schemas
│   ├── api/
│   │   ├── auth.py          # JWT utilities + FastAPI dependencies
│   │   └── routes/
│   │       ├── auth_route.py       # /api/v1/auth/*
│   │       ├── orgs_route.py       # /api/v1/orgs/*
│   │       ├── risks_route.py      # /api/v1/risks/*
│   │       ├── controls_route.py   # /api/v1/controls/*
│   │       ├── canvas_route.py     # /api/v1/canvas/*
│   │       ├── audit_route.py      # /api/v1/audit/*
│   │       ├── radar_route.py      # /api/v1/radar/*
│   │       ├── pulse_route.py      # /api/v1/pulse/*
│   │       ├── copilot_route.py    # /api/v1/copilot/*
│   │       └── dashboard_route.py  # /api/v1/dashboard
│   ├── ai/
│   │   ├── fingerprint.py   # Company fingerprinting pipeline
│   │   ├── copilot.py       # Claude-powered audit assistant
│   │   └── relevance.py     # Signal relevance scoring engine
│   ├── workers/
│   │   └── tasks.py         # Celery tasks — radar ingest + pulse checks
│   └── realtime/
│       └── websocket.py     # WebSocket — canvas collab + live signals
├── db/
│   └── migrations/
│       └── 001_initial_schema.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

## API reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Register user + create org |
| POST | `/api/v1/auth/login` | Get access + refresh tokens |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| GET | `/api/v1/auth/me` | Current user profile |
| POST | `/api/v1/orgs/fingerprint` | AI fingerprint a company name |
| POST | `/api/v1/orgs/complete-onboarding` | Seed org from fingerprint |
| GET | `/api/v1/dashboard` | Aggregated dashboard data |
| GET | `/api/v1/risks` | List risks (filterable) |
| POST | `/api/v1/risks` | Create risk |
| PATCH | `/api/v1/risks/{id}` | Update risk |
| GET | `/api/v1/controls` | List controls |
| POST | `/api/v1/controls/{id}/evidence` | Upload evidence file |
| GET | `/api/v1/canvas` | Full canvas (nodes + edges) |
| POST | `/api/v1/canvas/nodes` | Create canvas node |
| POST | `/api/v1/canvas/edges` | Connect two nodes |
| GET | `/api/v1/radar/signals` | List radar signals |
| GET | `/api/v1/pulse` | Control pulse summary |
| POST | `/api/v1/copilot` | Chat with AI co-pilot |
| POST | `/api/v1/audit/plans` | Create audit plan (AI-seeded) |
| WS | `/ws?token=<jwt>` | WebSocket for live collaboration |

## Key design decisions

**Multi-tenancy**: Row-level security on all `org_id`-scoped tables. Every query is automatically filtered by the authenticated user's org.

**Async throughout**: `asyncpg` driver with SQLAlchemy async sessions. All I/O — database, HTTP, AI — is non-blocking.

**AI fingerprinting**: On company name submission, five parallel tasks run via `asyncio.gather`: registry lookup, industry classification, process inference, risk taxonomy, framework suggestion. Two tasks use Claude; the rest use external APIs.

**Background jobs**: Radar ingestion and control pulse checks run as Celery tasks. The API never blocks on external sources — everything is eventual consistency with WebSocket push for live updates.

**WebSocket rooms**: Each org gets a room. Live cursors, node moves, and new signals are broadcast to all connected clients in the org's room. JWT token is passed as a query parameter (WebSocket headers are not supported in browsers).

## Environment variables

See `.env.example` for the complete list. The minimum required for a working local setup:

```env
DATABASE_URL=postgresql+asyncpg://aegis:aegis@localhost:5432/aegis
ANTHROPIC_API_KEY=sk-ant-...
SECRET_KEY=any-long-random-string
JWT_SECRET_KEY=another-long-random-string
```

## Production deployment

Recommended stack:
- **API**: [Railway](https://railway.app) or [Render](https://render.com) — deploy from this repo
- **Database**: [Supabase](https://supabase.com) — PostgreSQL + pgvector + RLS built in
- **Redis**: [Upstash](https://upstash.com) — serverless Redis
- **Storage**: [Cloudflare R2](https://www.cloudflare.com/products/r2/) — S3-compatible, no egress fees
- **Auth**: Consider migrating to [Clerk](https://clerk.com) for SSO + RBAC in production
