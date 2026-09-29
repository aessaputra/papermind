# AGENTS.md

## Project Overview

**PaperMind** — A production-grade full-stack Retrieval-Augmented Generation (RAG) system for chatting with PDF documents using Bring Your Own Key (BYOK). Users upload PDFs, which are parsed, chunked, and embedded into Supabase `pgvector` with customizable vector dimensions. Questions are answered via LLMs (Gemini, OpenAI, OpenRouter, OpenAI-Compatible) with page-level citations streamed back as Server-Sent Events (SSE).

### Architecture

The project follows a **two-service monorepo** layout:

```
papermind/
├── backend/          # FastAPI REST + SSE API (Python)
├── frontend/         # Next.js 15 App Router (TypeScript)
├── supabase/         # SQL migrations for Supabase PostgreSQL
├── docker-compose.yml          # Dev environment
├── docker-compose.prod.yml     # Production overrides
└── .agents/skills/             # AI coding agent skills
```

| Layer | Stack |
|---|---|
| **Frontend** | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS v4, `@supabase/ssr`, `@radix-ui/react-icons` |
| **Backend** | FastAPI, Pydantic v2, PyJWT, Cryptography (AES-256-GCM), Uvicorn |
| **RAG Pipeline** | LangChain (`langchain-google-genai`, `langchain-openai`, `langchain-ollama`), PyPDF |
| **Database** | Supabase PostgreSQL, `pgvector` (flexible unconstrained VECTOR), Supabase Auth (JWT) |
| **Containers** | Docker multi-stage builds, Docker Compose (dev + prod) |

### Key Design Decisions

- **Bring Your Own Key (BYOK)**: Users manage their own API keys encrypted with **AES-256-GCM** di backend (`CryptoService`).
- **Multi-Provider LLM & Custom Endpoints**: Supports Google Gemini, OpenAI (GPT-4o / GPT-4o-mini), OpenRouter, and OpenAI-Compatible custom endpoints (Groq, Together AI, vLLM, LM Studio) via dynamic factory in `backend/app/services/llm_factory.py`.
- **Dynamic Embedding & Embedding Lock**: Supports flexible vector dimensions (768d, 1536d, 3072d). Upon uploading the first document, user's chosen embedding model is automatically locked (`locked = true`) to maintain vector store consistency.
- **JWT Auth & Hard Block UX**: Backend validates Supabase JWTs. If a user lacks active provider/embedding keys, API endpoints return HTTP 403 Forbidden and frontend enforces a visual hard block guiding them to `/settings`.
- **SSE Streaming**: Chat responses stream token-by-token via Server-Sent Events through `backend/app/routers/chat_router.py` → `backend/app/services/rag_service.py`.
- **Row Level Security (RLS)**: All Supabase tables enforce RLS with cached policy evaluation `((select auth.uid()) = user_id)`.

---

## Setup Commands

### Prerequisites

- Python 3.11+ with `venv`
- Node.js 18+ with `npm`
- A Supabase project (for PostgreSQL + Auth)

### 1. Database Setup (Supabase)

1. Open your Supabase Dashboard → SQL Editor or use Supabase CLI.
2. Execute migration files in order from `supabase/migrations/`:
   - `20260723000000_init_rag_schema.sql` — Creates base tables (`documents`, `document_chunks`, `chat_sessions`, `chat_messages`) and initial RLS policies.
   - `20260724000000_harden_grants_and_rpc.sql` — Hardens grants and adds RPC functions.
   - `20260725000000_create_user_provider_configs.sql` — Creates `user_provider_configs` table with RLS and AES-256 encrypted key storage.
   - `20260725000001_create_user_embedding_configs_and_unconstrain_vector.sql` — Creates `user_embedding_configs` table, alters `document_chunks.embedding` to unconstrained `VECTOR`, and updates `match_document_chunks` RPC function.

Or push directly via CLI:
```bash
npx supabase db push --db-url "<YOUR_POSTGRES_DB_URL>"
```

### 2. Backend Setup (FastAPI)

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env — required keys:
#   SUPABASE_URL, SUPABASE_SECRET_KEY (or SUPABASE_SERVICE_ROLE_KEY),
#   SETTINGS_ENCRYPTION_KEY (32-byte secret key for AES-256 GCM)

# Run dev server
uvicorn app.main:app --reload --port 8000
```

Backend runs at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`.

### 3. Frontend Setup (Next.js 15)

```bash
cd frontend

# Install dependencies
npm install

# Configure environment variables
cp .env.example .env.local
# Edit .env.local — required keys:
#   NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
#   NEXT_PUBLIC_API_URL (defaults to http://localhost:8000)

# Run dev server
npm run dev
```

Frontend runs at `http://localhost:3000`.

---

## Development Workflow

### Running Services Locally

- **Backend**: `cd backend && uvicorn app.main:app --reload --port 8000`
- **Frontend**: `cd frontend && npm run dev`
- Both must run simultaneously; the frontend proxies API calls to the backend at `NEXT_PUBLIC_API_URL`.

### Running with Docker Compose (Development)

```bash
# Ensure backend/.env and frontend/.env are configured
docker compose up --build -d

# Verify backend health
curl http://localhost:8000/health
# Returns: {"status": "online"}
```

Hot-reloading is enabled via bind mounts in the dev docker-compose.yml.

### Environment Variables

#### Backend (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `SUPABASE_URL` | ✅ | Supabase project URL |
| `SUPABASE_SECRET_KEY` | ✅ | Supabase service role key (alias: `SUPABASE_SERVICE_ROLE_KEY`) |
| `SETTINGS_ENCRYPTION_KEY` | ✅ | Secret key for AES-256-GCM encryption of user API keys |
| `SUPABASE_JWT_SECRET` | ❌ | HMAC JWT signing secret (fallback if JWKS not configured) |
| `SUPABASE_JWKS_URL` | ❌ | Supabase JWKS endpoint for asymmetric JWT verification |
| `SUPABASE_JWT_AUDIENCE` | ❌ | JWT audience claim (default: `authenticated`) |

#### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | ✅ | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | ✅ | Supabase anon/publishable key |
| `NEXT_PUBLIC_API_URL` | ✅ | Backend API base URL (default: `http://localhost:8000`) |

---

## Testing Instructions

### Backend Tests (pytest)

All tests are in `backend/tests/` and use `pytest` + `pytest-asyncio`:

```bash
cd backend

# Activate virtual environment first
venv\Scripts\activate   # Windows
source venv/bin/activate  # Linux/macOS

# Run all tests (59 tests across 10 test files)
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_settings_router.py -v
```

#### Test Files and Coverage

| File | Tests | Coverage |
|---|---|---|
| `test_auth.py` | 6 | JWT verification (HMAC, expired, missing claims, JWKS) |
| `test_config.py` | 3 | Pydantic Settings loading, env var aliases |
| `test_crypto.py` | 5 | AES-256-GCM encryption/decryption, nonces, masking |
| `test_document_management.py` | 9 | Document list/toggle/preview/delete endpoints & StorageService |
| `test_embedding_migration.py` | 2 | Flexible unconstrained vector formatting & embedding schema |
| `test_ingestion.py` | 9 | Paragraph chunking, HyDE question generation, background document processing (happy + LLM rate limit + unparsable PDF) |
| `test_llm_factory.py` | 4 | Dynamic BYOK instantiation (Gemini, OpenAI, OpenRouter, Custom) |
| `test_rag.py` | 10 | RAG SSE streaming, citation extraction, prompt engineering patterns |
| `test_routers.py` | 4 | FastAPI endpoint health, auth integration & async upload dispatch |
| `test_settings_router.py` | 7 | Provider Configs CRUD, Presets, Embedding Lock enforcement & model verification |

### Frontend Verification

```bash
cd frontend
npm run build   # TypeScript type-check + Next.js production build
```

---

## Code Style

### Python (Backend)

- **Pydantic v2** models with `model_config = ConfigDict(...)`.
- **Type hints** on all function signatures.
- **Docstrings** on all modules, classes, and public functions.
- **Imports**: Standard library → third-party → local (`app.*`).
- **Dependencies**: Use FastAPI `Depends()` for injection. Auth uses `CurrentUserDep = Annotated[UserPayload, Depends(get_current_user)]`.

### TypeScript (Frontend)

- **Strict mode** enabled (`"strict": true` in `tsconfig.json`).
- **Path alias**: `@/*` maps to `./src/*`.
- **React 19** + **Next.js 15 App Router** conventions.
- **Styling**: Minimalist UI supporting both Light and Dark themes with Tailwind CSS v4.

---

## API Routes

### Backend (FastAPI)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | ❌ | Health check |
| `GET` | `/api/settings/providers` | ✅ Bearer | List user's configured AI providers |
| `POST` | `/api/settings/providers` | ✅ Bearer | Create a new AI provider config (AES-256 encrypted) |
| `PUT` | `/api/settings/providers/{id}` | ✅ Bearer | Update an existing AI provider config |
| `DELETE` | `/api/settings/providers/{id}` | ✅ Bearer | Delete an AI provider config |
| `GET` | `/api/settings/embedding/presets` | ❌ | List recommended embedding model presets |
| `GET` | `/api/settings/embedding` | ✅ Bearer | Get user's active embedding config & lock status |
| `POST` | `/api/settings/embedding` | ✅ Bearer | Save user's embedding config (Rejects if locked) |
| `POST` | `/api/documents/upload` | ✅ Bearer | Upload PDF, register document (`processing`) and ingest asynchronously via `BackgroundTasks` |
| `GET` | `/api/documents` | ✅ Bearer | List user's documents |
| `DELETE` | `/api/documents/{document_id}` | ✅ Bearer | Delete a document |
| `POST` | `/api/chat/stream` | ✅ Bearer | RAG query with SSE streaming response |
| `GET` | `/api/chat/sessions` | ✅ Bearer | List user's chat sessions |

All authenticated endpoints require a Supabase JWT in the `Authorization: Bearer <token>` header.

---

## Build and Deployment

### Production Docker
Use the production overrides to run optimized containers:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

### Manual Production Builds
- **Backend**: Uvicorn should be run with a production-ready configuration (e.g., specifying workers).
- **Frontend**: 
  ```bash
  cd frontend
  npm run build
  npm start
  ```

---

## Security Considerations

- **Bring Your Own Key (BYOK)**: All API keys must be encrypted before database storage using AES-256-GCM (`CryptoService`). Do not log API keys in plain text.
- **Row Level Security (RLS)**: Every Supabase table must have RLS enabled with policies ensuring users can only access their own data (`(select auth.uid()) = user_id`).
- **Authentication**: JWT verification is mandatory for all protected FastAPI routes using `CurrentUserDep`.

---

## Pull Request Guidelines

- **Title Format**: `[Frontend/Backend/Fullstack/Docs] Brief description of changes`
- **Required Checks**:
  - **Backend**: `python -m pytest tests/` must pass with no errors.
  - **Frontend**: `npm run build` must successfully compile the TypeScript code.
- **Scope**: Ensure changes to one service do not break the API contracts for the other service. Test the full RAG pipeline locally before requesting a review.
