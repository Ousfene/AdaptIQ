# AdaptIQ — Adaptive Learning Platform

An intelligent learning platform that adapts to each learner's 
ability level in real time using Item Response Theory, LLM-powered 
content generation, and competitive multiplayer modes.

## Study Modes

| Mode | Description |
|---|---|
| **Classic** | Server-driven adaptive practice — difficulty adjusts per answer |
| **Challenge** | Level-based progression with streaks and ranked play |
| **Custom** | Topic-focused learning with per-concept mastery tracking |
| **PvP** | 1v1 competitive sessions with Elo matchmaking and leaderboard |
| **Visual** | Image-based quiz experiences |

## Core Features

- **IRT Engine** — tracks per-concept ability estimates and selects 
questions within each learner's Zone of Proximal Development
- **RAG Pipeline** — multi-source retrieval (Wikipedia, Wikidata, 
Hugging Face, DBpedia) grounding LLM outputs with full citation 
traceability
- **Elo Matchmaking** — K-factor 32/16 rating system with 
synchronized 1v1 PvP sessions and post-match rating updates
- **Content Governance** — admin-configurable block rules, 
answer-leakage detection, and full audit logging
- **Admin Dashboard** — standalone dashboard for monitoring users, 
sessions, concepts, and governance rules

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy async, Pydantic v2 |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS |
| Database | PostgreSQL (26 tables) |
| Cache | Redis |
| LLM | Groq API (Llama), RAG pipeline |
| Auth | JWT with ownership validation |
| DevOps | Docker Compose |
| Testing | pytest, React lint + build |

## Architecture

React Frontend (Vite)
↓
FastAPI Backend (/api/)
↓              ↓
PostgreSQL         Redis
(persistence)    (sessions/cache)
↓
RAG Pipeline
(Wikipedia · Wikidata · HuggingFace · DBpedia)
↓
Groq LLM (Llama)
(question/hint generation)

## Project Structure

├── backend/
│   ├── main.py                  # App entry point
│   ├── config.py                # Environment settings
│   ├── routers/                 # API route handlers
│   ├── services/                # Business logic
│   ├── models/                  # SQLAlchemy models
│   ├── migrations/              # Database migrations
│   └── tests/                   # pytest test suite
├── frontend/
│   ├── src/
│   │   ├── pages/               # Route-based page components
│   │   └── components/          # Shared UI components
│   └── vite.config.ts
├── admin_dashboard.html         # Standalone admin UI
├── admin_server.py              # Admin dashboard server
└── docs/                        # Documentation and reports

## API Overview

Backend serves all routes under `/api/`. Key route groups:

- `/api/auth/` — signup, login, profile, stats, password reset
- `/api/rooms/classic/` — adaptive question generation and answers
- `/api/challenge/` — level progression, streaks, ranked sessions
- `/api/custom/` — topic/concept selection and mastery tracking
- `/api/pvp/` — queue, matchmaking, match flow, Elo ratings
- `/api/admin/` — users, sessions, concepts, DB schema, monitoring
- `/api/admin/governance/` — block rules and audit logs
- `GET /health` — health check

Full interactive docs available at `http://localhost:8000/docs`

## Quick Start

### 1. Start infrastructure

```bash
cd backend
docker compose up -d
```

### 2. Run backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Backend: `http://localhost:8000`
Docs: `http://localhost:8000/docs`

### 3. Run frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:3000`

### 4. Optional admin dashboard

```bash
python admin_server.py
```

## Environment Variables

Create a `.env` file in `backend/`:

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost/adaptiq
REDIS_URL=redis://localhost:6379
JWT_SECRET_KEY=your-strong-secret-32-chars-minimum
GROQ_API_KEY=your-groq-api-key
ENVIRONMENT=development
AUTO_CREATE_TABLES=true
CORS_ORIGINS=http://localhost:3000
```

See `backend/config.py` for all available settings.

## Security

- JWT authentication on all protected routes
- User-scoped ownership validation
- Server-side session and answer state validation
- Admin-only endpoints with privilege checks
- Production startup blocks unsafe dev settings
- Content governance with configurable block rules and audit trail

## Testing

```bash
# Full test suite
cd backend && python -m pytest -q tests

# Security and PvP regression tests
python -m pytest -q tests/test_pvp_admin_regressions.py \
                    tests/test_security_regressions.py

# Frontend
cd frontend && npm run lint && npm run build
```

## License

MIT
