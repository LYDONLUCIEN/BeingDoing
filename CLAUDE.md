# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BeingDoing ("找到想做的事") is an intelligent guidance system that helps users discover their true calling through exploring values, strengths, and interests. Core formula: **Likes × Talents × Values = True Calling**.

Full-stack app: Next.js 14 frontend + FastAPI backend + LangGraph agent.

## Commands

### Backend (from `src/backend/`)
```bash
pip install -r requirements.txt          # install deps
alembic upgrade head                     # run migrations
python scripts/init_db.py                # seed database
uvicorn app.main:app --reload            # dev server (port 8000)
```

### Frontend (from `src/frontend/`)
```bash
npm install                              # install deps
npm run dev                              # dev server (port 3000)
npm run build                            # production build
npm run lint                             # ESLint
```

### Tests (from project root)
```bash
pytest                                   # all backend tests
pytest test/backend/core/agent/          # agent tests only
pytest -k test_name                      # single test by name
pytest --cov=app --cov-report=html       # with coverage
```
pytest.ini sets `pythonpath = src/backend` and `asyncio_mode = auto`, so async tests work without decorators.

### Docker
```bash
docker-compose up -d                     # backend:8000, frontend:3000, postgres:5432
```

## Architecture

### Agent System (core of the app)

The agent uses LangGraph to implement a ReAct thinking chain in `src/backend/app/core/agent/`:

```
reasoning_node → action_node → observation_node → [loop back or end] → user_agent_node → END
```

- **reasoning_node**: Analyzes user input, decides action (use_tool / respond / guide). Uses YAML prompt templates from `app/domain/prompts/`.
- **action_node**: Executes tools or sets `final_response`.
- **observation_node**: Processes tool results, decides whether to continue looping.
- **user_agent_node**: Converts internal thinking chain output into user-visible `messages`.
- **guide_node**: Proactive guidance triggered by idle/quiet timeouts.

**Dual-track state** (`AgentState` in `state.py`):
- `messages` — user-visible output (written by user_agent_node)
- `inner_messages` — internal thinking chain (reasoning/observation), never exposed to frontend
- `logs` — process logs for frontend progress display

**Tools** (registered via `ToolRegistry`): `SearchTool`, `GuideTool`, `ExampleTool`.

### Request Flow

```
POST /api/v1/chat/messages
  → chat.py → create_agent_graph(config) → create_initial_state(...)
  → graph.astream(state) → thinking chain loop → final messages
  → StandardResponse { code, message, data }
```

Streaming uses SSE via `GET /api/v1/chat/messages/stream` with `asyncio.Queue`.

### Exploration Flow Steps

Defined in `src/backend/app/domain/steps.py` (single source of truth):
1. `values_exploration` — explore values (价值观)
2. `strengths_exploration` — explore talents (才能)
3. `interests_exploration` — explore interests (热情)
4. `combination` — combine the three elements
5. `refinement` — refine and validate results

`STEP_TO_CATEGORY` maps step IDs to knowledge categories (values/strengths/interests).

### Backend Structure

- `app/api/v1/` — FastAPI routes (auth, chat, sessions, answers, search, formula)
- `app/services/` — business logic layer
- `app/core/agent/` — LangGraph agent (graph, state, nodes, tools, config)
- `app/core/knowledge/` — knowledge base loader (CSV/Markdown) and searcher
- `app/core/llmapi/` — LLM provider abstraction (OpenAI)
- `app/domain/` — flow steps, knowledge config, prompt templates
- `app/models/` — SQLAlchemy ORM models (User, Session, Answer, Progress, etc.)
- `alembic/` — database migrations

### Frontend Structure

- `app/` — Next.js 14 App Router pages (explore, auth, profile, admin)
- `components/explore/` — conversation thread, answer cards, step progress
- `lib/api/` — Axios-based API client with JWT interceptor (`client.ts` + per-resource modules)
- `stores/` — Zustand stores with localStorage persistence (auth, session, progress)

### Database

SQLAlchemy 2.0+ async. Default: SQLite (`aiosqlite`). Production: PostgreSQL (`asyncpg`).

Key models: User → Session → Answer/Progress. Questions loaded from knowledge base files.

### Configuration

Environment variables (`.env` at project root):
- `OPENAI_API_KEY` — required
- `SECRET_KEY` — JWT secret, required
- `DATABASE_URL` — default `sqlite+aiosqlite:///./app.db`
- `ARCHITECTURE_MODE` — `simple` (default) or `full`
- `LLM_MODEL` — default `gpt-4`
- `AUDIO_MODE` — enable ASR/TTS (default False)

Settings loaded in `src/backend/app/config/settings.py`.

## Key Patterns

- All backend routes and DB operations are async (`async def`, `AsyncSession`).
- API responses use `StandardResponse { code, message, data }` format.
- Agent graph is configurable via `AgentRunConfig` — `use_user_agent_node` can be toggled for debugging.
- Knowledge base files (CSV) are in the project root: `重要的事_价值观.csv`, `喜欢的事_热情.csv`, `擅长的事_才能.csv`.
- The project is bilingual — code is in English, UI text and comments are in Chinese.
