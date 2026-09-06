# SIH26100: AI-Powered Integrated Bid Compliance Verification Platform for GeM Procurement

An enterprise-grade, zero-hallucination compliance verification platform for Government e-Marketplace (GeM) tenders. It evaluates complex multi-page bidder proposals against tender specifications using a **hybrid intelligence engine** (Deterministic Rule Validation + NVIDIA NIM LLM Semantic Analysis with verifiable page citations).

---

## 🚀 Technology Stack

- **Frontend**: Next.js 15, React 19, TypeScript, Tailwind CSS, Lucide Icons
- **Backend**: FastAPI (Python 3.12+), SQLAlchemy 2.0 (Async), Pydantic v2
- **Database**: PostgreSQL 16 with `pgvector` extension for semantic evidence search
- **LLM Inference**: NVIDIA NIM API (`openai/gpt-oss-20b`)
- **PDF Extraction**: PyMuPDF (`fitz`) with Tesseract OCR fallback
- **Containerization**: Docker & Docker Compose

---

## 📂 Project Structure

```
SIH-Project/
├── docker/
│   ├── docker-compose.yml       # Multi-container orchestration (DB, API, Web)
│   ├── Dockerfile.backend       # FastAPI backend container
│   └── Dockerfile.frontend      # Next.js frontend container
├── backend/
│   ├── app/
│   │   ├── api/v1/              # API endpoints (health, tenders, bidders, evaluations)
│   │   ├── core/                # Config, async database session, pgvector initialization
│   │   ├── models/              # SQLAlchemy models (Tender, Clause, Bidder, Evaluation)
│   │   ├── schemas/             # Pydantic schemas for request & response validation
│   │   ├── services/            # NVIDIA NIM client wrapper, Rule engine, Evaluator
│   │   └── main.py              # FastAPI application entry point
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/                 # Next.js App Router (Dashboard, Upload, Matrix)
│   │   ├── components/          # Reusable UI components
│   │   └── lib/                 # API client and shared TypeScript types
│   ├── package.json
│   └── tsconfig.json
├── .env.example
└── README.md
```

---

## ⚡ Quickstart

### Prerequisites
- Docker & Docker Compose **OR** Python 3.12+ & Node.js 20+
- NVIDIA NIM API Key (Set in `.env`)

### Option 1: Run with Docker Compose (Recommended)

1. Copy the environment variables:
   ```bash
   cp .env.example .env
   ```
2. Add your NVIDIA API key in `.env`:
   ```env
   NVIDIA_API_KEY="nvapi-your-key-here"
   ```
3. Start all services:
   ```bash
   docker compose -f docker/docker-compose.yml up --build
   ```
4. Access:
   - **Frontend UI**: [http://localhost:3000](http://localhost:3000)
   - **FastAPI Backend Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
   - **Health Check**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

---

### Option 2: Run Locally (Development Mode)

#### 1. Backend Setup
```bash
cd backend
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

#### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

---

## 🛡️ Day 1 Scaffolding Verification

- [x] Docker multi-container setup with PostgreSQL + pgvector
- [x] FastAPI async application structure with health check endpoints
- [x] SQLAlchemy models for Tenders, Clauses, Bidders, Chunks, and Evaluations
- [x] NVIDIA NIM client wrapper configured with `openai/gpt-oss-20b`
- [x] Next.js frontend with Tailwind CSS and system status dashboard
