# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**开发规范请严格遵循 [claude-开发文档.md](./claude-开发文档.md)**（代码分层、命名、提交、测试要求）。

## Project Overview

BeingDoing is a full-stack AI-powered career guidance system (Chinese-language UI) that helps users discover their calling through exploring values, talents, and interests. Core formula: **Passion x Talent x Values = True Calling**.

## Commands

### Service Management (tmux-based)
```bash
./start.sh              # Start backend + frontend (default dev mode)
./start.sh start-dev    # Dev mode (frontend: next dev --turbo)
./start.sh start-run    # Production mode (clean .next, build, start)
./start.sh stop         # Stop all services
./start.sh restart      # Restart all
./start.sh restart backend   # Restart only backend
./start.sh restart frontend  # Restart only frontend
./start.sh attach       # Reattach to tmux session
```

### Backend
```bash
cd src/backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
alembic upgrade head          # Run database migrations
python scripts/init_db.py     # Initialize database
```

### Frontend
```bash
cd src/frontend
npm run dev       # Dev server with turbo on port 3000
npm run build     # Production build
npm run lint      # ESLint
```

### Testing
```bash
pytest                              # Run all tests (from repo root)
pytest test/test_foo.py             # Run single test file
pytest test/test_foo.py::test_bar   # Run single test
pytest --cov=app --cov-report=html  # Coverage report
```
pytest is configured with `pythonpath = src/backend` and `asyncio_mode = auto`.

### Docker
```bash
docker-compose up -d    # Start all (backend, frontend, PostgreSQL)
```

### Code Formatting
- Python: Black (line-length=100, target py310), isort (black profile)
- TypeScript: ESLint via `next lint`

## Architecture

### Layer Structure
```
Frontend (Next.js 14, port 3000)
    ↓ HTTP
API Layer (FastAPI v1 routes, port 8000)
    ↓
Business Services (src/backend/app/services/)
    ↓
Core Services (src/backend/app/core/)
    ↓
Data Layer (SQLite dev / PostgreSQL prod)
```

### Backend (`src/backend/app/`)
- **`api/v1/`** — Route handlers. Key endpoints: `auth`, `chat`, `chat_optimized`, `simple_auth`, `simple_chat`, `sessions`, `questions`, `answers`, `admin`, `export`, `analytics`, `audio`
- **`services/`** — Business logic: auth, user, answer, guide, session, progress, export, analytics, email
- **`core/`** — Infrastructure:
  - `llmapi/` — Unified LLM provider interface (`BaseLLMProvider`). Supports OpenAI, DeepSeek, Kimi, Qwen
  - `agent/` — LangGraph-based ReAct agent with nodes (reasoning, action, observation, guide) and tools (SearchTool, GuideTool, ExampleTool)
  - `knowledge/` — CSV/Markdown knowledge base loader + keyword search
  - `asr/`, `tts/` — Optional speech services (controlled by `AUDIO_MODE` env var)
  - `database/` — SQLAlchemy models and DB initialization
- **`models/`** — SQLAlchemy models: User, Session, Question, Answer, Progress, Analytics, RefreshToken
- **`config/settings.py`** — Centralized settings from environment variables

### Frontend (`src/frontend/`)
- **Next.js 14 App Router** (`app/`):
  - `auth/` — Login/register pages
  - `(main)/dashboard/` — User dashboard
  - `(main)/explore/` — Core exploration flow (values, talents, interests)
- **`components/`** — React components (explore, admin, layout, survey)
- **`stores/`** — Zustand state management
- **`lib/`** — Utilities and API client (Axios)

### Key Configuration
- `.env` at repo root — LLM provider, API keys, database URL, `ARCHITECTURE_MODE` (simple/full), `AUDIO_MODE`, `FRONTEND_MODE`
- The `start.sh` script unsets conflicting env vars before sourcing `.env` to prevent cross-project contamination
- Backend uses conda environment `py312` (configured in `start.sh`)

### Data Files
- `data/` — Conversation records, knowledge base files
- Root-level CSV files — Knowledge base content for values, passion, and talent exploration (Chinese filenames)
