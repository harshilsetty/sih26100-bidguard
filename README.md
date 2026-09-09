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

---

## 🏛️ Phase 6 — Mock Integrated Verification Foundation

### 1. Purpose & Strategic Value
In public procurement on the Government e-Marketplace (GeM), bidder self-declarations and uploaded PDFs cannot be relied upon in isolation. Unscrupulous bidders may inflate turnover, falsely claim Micro/Small Enterprise (MSE) exemption benefits, submit fabricated Make in India (MII) local content certificates, or operate under inactive/cancelled statutory registrations.

Phase 6 establishes the architectural foundation for **Multi-Source Cross-Verification**. It models authoritative government registers as isolated, typed contracts and deterministic synthetic datasets, allowing the platform to detect cross-source contradictions and verify statutory eligibility before contract award.

> **CRITICAL DISCLAIMER**:
> **No live government portal/API data is used in this phase.**
> All external verification data consists strictly of deterministic, synthetic mock records generated for the Smart India Hackathon (SIH 2026) demonstration. No real government credentials, live API calls, private corporate data, or real PII are utilized.

### 2. Five Authoritative Mock Source Domains
The verification foundation models 5 key government registries:

| Domain | Source Code | Primary Identity | Key Attributes Verified | Synthetic Records |
| :--- | :--- | :--- | :--- | :--- |
| **GSTN** | `GSTN` | GSTIN (15 chars) | Annual verified turnover, registration status, filing regularity | 1,000 |
| **Udyam / MSME** | `UDYAM` | Udyam Reg. No. | Enterprise classification (Micro/Small/Medium), statutory MSE exemption status | 1,000 |
| **MCA** | `MCA` | CIN (21 chars) | Corporate legal name, company status (ACTIVE/STRUCK OFF), ROC state | 1,000 |
| **Income Tax / PAN** | `INCOME_TAX` | PAN (10 chars) | Entity identity match, PAN status (ACTIVE/INOPERATIVE/CANCELLED), ITR status | 1,000 |
| **Make in India (MII)** | `MII` | Audit Verification ID | Verified domestic local content %, Class-I/II certification, auditor reference | 1,000 |
| **TOTAL** | | | | **5,000 Records** |

### 3. Architecture & Database Deployment Hardening
- **Canonical Runtime Database**: **PostgreSQL 16** with the `pgvector` and `uuid-ossp` extensions is the authoritative runtime database across staging, demo, and production environments.
- **5,000 Mock Records Stored in PostgreSQL**: All 5,000 deterministic synthetic records across GSTN, Udyam, MCA, Income Tax, and MII are seeded and queried directly from PostgreSQL tables (`mock_gstn_records`, `mock_udyam_records`, etc.).
- **Explicit SQLite Fallback Guard (`ALLOW_SQLITE_FALLBACK=False`)**: Automatic SQLite fallback is strictly **disabled by default** (`ALLOW_SQLITE_FALLBACK: bool = False`). If PostgreSQL is unavailable, the application **fails fast** with a clear `RuntimeError` rather than silently continuing, preventing split-brain or data divergence.
- **Local Development Exception**: SQLite fallback (`sqlite+aiosqlite:///gem_compliance.db`) is only permitted when `ALLOW_SQLITE_FALLBACK=true` is explicitly configured for offline local testing without PostgreSQL.
- **Health Diagnostic Endpoint**: The `/api/v1/health` endpoint exposes the active database engine (`"database": "postgresql"`, `"status": "healthy"` or `"database": "sqlite_fallback"`, `"status": "degraded"`).
- **Source Boundary Rule**: Bidder self-declarations (e.g. ₹8.0 Cr turnover in a PDF proposal) remain in the bidder document layer. Authoritative registry records (e.g. ₹3.65 Cr verified turnover on GSTN) reside exclusively in government source tables. Neither domain mutates the other.
- **Explicit Mock Labeling**: Every synthetic record permanently carries `is_mock = True` and `source_type = "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"` to guarantee it can never be mistaken for live government records.
- **Deterministic Generation & Idempotent Seeding**: Built on seed `26100`. Fixtures in `backend/mock_data/*.json` provide 5,000 deterministic records. `python -m app.services.mock_seeder` can be executed repeatedly with zero record duplication.

### 4. Deterministic Showcase Bidders & Contradiction Scenarios
The dataset defines 10 fixed showcase bidders (`BIDDER-01` through `BIDDER-10`) with mapped identities across all 5 source registries, priming future cross-source compliance rules:
1. **Turnover Contradiction**: `BIDDER-10` declares ₹8.00 Cr in proposal documents, while GSTN mock records verify only ₹3.65 Cr.
2. **MSE Exemption Verification**: `BIDDER-03` legitimately qualifies for tender fee/EMD exemptions via `ACTIVE` + `MICRO` status on Udyam.
3. **Local Content Contradiction**: `BIDDER-10` claims 50% domestic content in its cover letter, but Bill of Materials (BOM) analysis and MII mock register confirm only 32% (disqualifying Class-I status).
4. **Entity Name Variation**: `BIDDER-04` proposal references "Alpha Technologies Pvt Ltd", whereas MCA registry lists "Alpha Technology Private Limited".
5. **Inactive/Cancelled Registrations**: `BIDDER-08` exhibits `CANCELLED` GSTN status and `INOPERATIVE` PAN status.

### 5. Current Limitations & Roadmap
- **Implemented in Phase 6.1 + 6.2**: Typed Pydantic schemas, SQLAlchemy ORM models, indexes, 5,000 deterministic synthetic records, idempotent seeder, 10 showcase bidder profiles, comprehensive test suite, and UI preview banner.
- **Subsequent Phases**:
  - *Phase 6.3*: Mock Source Providers & Gateway Adapters
  - *Phase 6.4*: Verification Gateway & Request Routing
  - *Phase 6.5*: Multi-Source Evidence Fusion
  - *Phase 6.6*: Cross-Source Contradiction Engine Integration
  - *Phase 6.7*: Statutory Risk Scoring & Bidder Qualification Ranking
  - *Phase 6.8*: Procurement Officer Verification UI Dashboard

### 6. Mock Data Explorer (Read-Only Inspection UI & API)
The platform includes a dedicated read-only **Mock Verification Data Explorer** accessible at route `/mock-data` and backed by `/api/v1/mock-sources`.

- **Source of Truth**: All records are queried directly from the relational database tables (`mock_gstn_records`, `mock_udyam_records`, etc.), not by reading raw JSON files directly in the frontend.
- **Read-Only Nature**: Strictly an inspection, administrative, and demonstration tool. It does not perform live verification or mutate evidence.
- **Top Summary & Dataset Integrity**: Live verification of the 5,000 synthetic records, confirming uniqueness of primary keys and verification IDs, and verifying 100% mock labeling.
- **Showcase Bidders Multi-Registry Inspector**: Provides a synchronized, 5-registry view for showcase bidders `BIDDER-01` through `BIDDER-10` to validate cross-source mappings prior to Phase 6.3.
- **Demo Scenarios**: Interactive inspection of the 5 planted contradiction fixtures (Turnover shortfall, MSE exemption, Make in India local content deficit, Entity legal name variation, and Inactive statutory registrations).
- **Server-Side Search & Pagination**: Search by GSTIN, CIN, PAN, Udyam number, company name, or category with page sizes from 25 to 100.
- **Export**: Generates clean, read-only CSV downloads per registry domain for external analysis.


