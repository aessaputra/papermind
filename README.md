# 📚 PaperMind System

> **A full-stack RAG (Retrieval-Augmented Generation) PDF chatbot project**
> Built with **FastAPI**, **LangChain**, **Supabase (`pgvector` & Auth)**, **Next.js 15 (App Router)**, **React 19**, **TypeScript**, and **Tailwind CSS v4**.

---

## 🌟 Key Features

- 📑 **Multi-File PDF Ingestion**: Drag-and-drop PDF upload with automatic text parsing (`pypdf`) and metadata preservation.
- ⚡ **Realtime SSE Token Streaming**: Server-Sent Events (SSE) token-by-token streaming response with live typing effect.
- 🎯 **Page-Level PDF Citations**: Exact page number references attached to AI answers with interactive side-drawer preview.
- 🤖 **Multi-Provider LLM Engine**: Seamless switching between **Google Gemini (Default)**, **OpenAI (GPT-4o mini)**, and **Ollama (Local Llama 3)**.
- 🔒 **Supabase Auth & RLS**: JWT Bearer token validation and Row Level Security with cached policy plan evaluation `((select auth.uid()) = user_id)`.
- 🎨 **Dark Theme UI**: Responsive dark mode UI built with Tailwind CSS v4 and Radix icons.

### How the interface works

1. Upload one or more PDFs in the document manager; the FastAPI backend registers each file, processes it in the background, and exposes its status to the UI.
2. Select documents and ask a question. The Next.js chat interface sends the request to the FastAPI RAG endpoint and renders streamed SSE tokens as they arrive.
3. Open a citation to inspect the cited page number and retrieved document context. Chat sessions can be reopened from the sidebar.

No public demo or screenshots are included in this repository; run locally with your own Supabase project and provider configuration using the steps below.

---

## 🛠️ Technology Stack

| Layer | Technology / Package |
|---|---|
| **Frontend** | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS v4, `@supabase/ssr`, Radix Icons |
| **Backend API** | FastAPI, PyYAML, PyJWT, Pydantic v2, Uvicorn |
| **RAG & Vector Store** | LangChain (`langchain-google-genai`, `langchain-openai`, `langchain-ollama`), PyPDF, Supabase Vector (`pgvector` HNSW index) |
| **Database & Auth** | Supabase PostgreSQL, Supabase Auth (HS256 JWT) |
| **Containerization** | Docker, Multi-Stage Dockerfile, Docker Compose |

---

## 🚀 Quick Start Guide

### 1. Database Setup (Supabase SQL Migration)

1. Open your [Supabase Dashboard](https://supabase.com/dashboard) -> SQL Editor.
2. Apply the migration scripts in `supabase/migrations/` in filename order.
3. This creates PostgreSQL tables (`documents`, `document_chunks`, `chat_sessions`, `chat_messages`), foreign key indexes, HNSW vector index (`vector_cosine_ops`), and cached RLS policies.

### 2. Backend Setup (FastAPI)

```bash
cd backend

# Create virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure Environment Variables (.env)
cp .env.example .env
# Edit .env and set your SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, and GEMINI_API_KEY

# Run backend tests (results depend on your environment and configuration)
python -m pytest tests/ -v

# Run FastAPI Server locally
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend Setup (Next.js 15)

```bash
cd frontend

# Install dependencies
npm install

# Configure Environment Variables (.env.local)
cp .env.example .env.local
# Edit .env.local and set NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY

# Run Next.js Dev Server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 🐳 Docker Deployment

To run the full-stack application (Backend FastAPI + Frontend Next.js 15) using Docker Compose:

```bash
# 1. Ensure backend/.env exists and is configured
cp backend/.env.example backend/.env

# 2. Build and start full-stack containers
docker compose up --build -d

# 3. Verify backend container health check
curl http://localhost:8000/health
# Returns: {"status": "online"}
```

Open [http://localhost:3000](http://localhost:3000) for the Next.js frontend and [http://localhost:8000/docs](http://localhost:8000/docs) for the FastAPI Swagger API documentation.

---

## 🧪 Testing & Verification

The backend includes tests for authentication, configuration, PDF ingestion, RAG streaming, and router endpoints. Run them in your configured environment; no passing count is claimed here without a current test run. Frontend automated tests are not included yet.

```bash
cd backend
python -m pytest tests/ -v
```

---

## 📄 License

MIT License.
