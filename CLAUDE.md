# Project Instructions — PaperMind

Two-service monorepo: `backend/` (FastAPI) + `frontend/` (Next.js 15 App Router). DB/Auth: Supabase Postgres + `pgvector`.

## Commands
- Backend dev: `cd backend && uvicorn app.main:app --reload --port 8000`
- Frontend dev: `cd frontend && npm run dev`
- Backend tests: `cd backend && python -m pytest tests/ -v`
- Frontend check: `cd frontend && npm run build`
- Docker dev: `docker compose up --build -d`; prod adds `-f docker-compose.prod.yml`

## Code Style
- Python: Pydantic v2 (`ConfigDict`), type hints on all signatures, docstrings on modules/classes/public fns, imports stdlib → third-party → `app.*`, DI via `Depends()` (`CurrentUserDep` for auth).
- TypeScript strict, path alias `@/*` → `./src/*`, Tailwind v4. Backend files `snake_case`, frontend components `PascalCase`.
- Errors: `app/exceptions.py` + `HTTPException` backend; SSE chat emits `citations` then `token` events.

## Key Constraints
- BYOK: user API keys AES-256-GCM encrypted (`CryptoService`) — never log plaintext.
- Embedding Lock: `user_embedding_configs` locked after first upload; vector col is unconstrained `VECTOR`.
- RLS on every table: `(select auth.uid()) = user_id`. JWT (`CurrentUserDep`) mandatory on protected routes.
- PR checks: `pytest` green + `npm run build` clean; don't break the FastAPI↔Next.js contract.

## Structure
- `backend/app/routers/` → `chat|document|settings_router.py`; `services/` → `rag_service|ingestion|llm_factory|context_retriever|prompt_builder|crypto_service|storage_service|...`
- `frontend/src/app/(auth)| (main)/` routes, `components/chat|settings|document-manager|auth|layout/`, `lib/api.ts`, `context/*Context.tsx`
- `supabase/migrations/` applied in filename order.
- Tests `backend/tests/test_*.py` (pytest + pytest-asyncio, 59 tests / 10 files).

## Commits
- Style: `feat:`, `test:`, `fix:`, or `[Backend]/[Frontend]/[Docs]` prefix. PR title: `[Frontend/Backend/Fullstack/Docs] ...`
