# SIH26100: AI-Powered Integrated Bid Compliance Verification Platform
# Production & Demo Deployment Guide

This document outlines the architecture, deployment procedures, operational runbooks, backup/restore workflows, and security considerations for deploying the **SIH26100 GeM Bid Compliance Verification Platform** in production and demonstration environments.

---

## 1. System Architecture

```
                                  INTERNET / INTRANET
                                          │
                                          ▼ [Port 80 HTTP / 443 HTTPS]
                             ┌─────────────────────────┐
                             │   Caddy Reverse Proxy   │
                             │ (Automatic TLS / SSL)   │
                             └────────────┬────────────┘
                                          │
               ┌──────────────────────────┴──────────────────────────┐
               │                                                     │
               ▼ [/api/*, /docs, /openapi.json]                      ▼ [/*]
    ┌──────────────────────────┐                          ┌──────────────────────────┐
    │  FastAPI Backend (Py3.12)│                          │ Next.js 15 Frontend      │
    │  Container: Port 8000    │                          │ Container: Port 3000     │
    └──────────┬───────────────┘                          └──────────────────────────┘
               │
               │ [Internal Docker Network only — NOT publicly exposed]
               ▼
    ┌──────────────────────────┐
    │ PostgreSQL 16 + pgvector │
    │ Container: Port 5432     │
    │ Volume: postgres_data    │
    └──────────────────────────┘
               │
               ▼ Outbound HTTPS only
    ┌──────────────────────────┐
    │ NVIDIA NIM Inference API │
    │ (openai/gpt-oss-20b)     │
    └──────────────────────────┘
```

---

## 2. Server Requirements

### Minimum Specifications (Demo / Evaluation)
- **CPU**: 2 vCPUs (x86_64 or ARM64)
- **RAM**: 4 GB RAM (8 GB recommended for concurrent PDF chunking)
- **Disk**: 25 GB SSD storage (accommodates Docker images, PostgreSQL volume, and tender uploads)
- **OS**: Ubuntu 22.04 / 24.04 LTS, Debian 12, or modern Linux distribution
- **Docker Engine**: Docker 24.0+ and Docker Compose v2.20+

### Production Specifications (High Concurrency)
- **CPU**: 4–8 vCPUs
- **RAM**: 16 GB RAM
- **Disk**: 100 GB NVMe storage with regular automated snapshots

---

## 3. Environment Variables & Secret Setup

Never commit production secrets to Git. Copy the production template and populate credentials:

```bash
cp .env.production.example .env.production
chmod 600 .env.production
```

### Required Variables Summary

| Variable | Description | Example / Recommendation |
|---|---|---|
| `DOMAIN` | Hostname for automatic HTTPS via Caddy | `gem-compliance.gov.in` (or `localhost` for demo) |
| `POSTGRES_USER` | PostgreSQL superuser/application user | `gem_admin` |
| `POSTGRES_PASSWORD` | Strong database password | Generate via `openssl rand -base64 32` |
| `POSTGRES_DB` | Application database name | `gem_compliance_prod` |
| `DATABASE_URL` | SQLAlchemy async driver URL | `postgresql+asyncpg://user:pass@postgres:5432/db` |
| `SYNC_DATABASE_URL` | SQLAlchemy sync driver URL | `postgresql://user:pass@postgres:5432/db` |
| `ALLOW_SQLITE_FALLBACK` | Runtime fallback guard | **MUST be `false` in production/demo** |
| `NVIDIA_API_KEY` | NVIDIA NIM Cloud API Key | `nvapi-...` (Backend only; never in frontend) |
| `NEXT_PUBLIC_API_URL` | Frontend API target | Leave empty (`""`) for single-domain routing |

---

## 4. Docker Deployment Commands

### Step 1: Start Production Stack
Run the production Compose file with the production environment file:

```bash
docker compose -f docker/docker-compose.prod.yml --env-file .env.production up -d --build
```

### Step 2: Verify Container Status & Health
Ensure all 4 containers start and report `healthy`:

```bash
docker compose -f docker/docker-compose.prod.yml ps
```

Expected Output:
```text
NAME                 IMAGE                     STATUS                    PORTS
gem_prod_db          pgvector/pgvector:pg16    Up (healthy)              5432/tcp
gem_prod_backend     docker-backend            Up (healthy)              8000/tcp
gem_prod_frontend    docker-frontend           Up (healthy)              3000/tcp
gem_prod_proxy       caddy:2-alpine            Up (healthy)              0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
```

### Step 3: Inspect Backend Logs & Idempotent Seeding
The backend entrypoint automatically initializes tables and seeds the 5,000 synthetic government records idempotently:

```bash
docker compose -f docker/docker-compose.prod.yml logs backend
```

Expected Log Snippet:
```text
==> Verifying database runtime...
    ALLOW_SQLITE_FALLBACK is set to: false
==> Running idempotent mock seeder & database initialization...
INFO:app.core.database:Database initialized successfully.
Seeding Results:
  GSTN        : Inserted=0     Existing=1000  Total=1000
  UDYAM       : Inserted=0     Existing=1000  Total=1000
  MCA         : Inserted=0     Existing=1000  Total=1000
  INCOME_TAX  : Inserted=0     Existing=1000  Total=1000
  MII         : Inserted=0     Existing=1000  Total=1000
Grand Total: Inserted 0 records. Total active records in DB: 5000
Idempotency guarantee verified.
==> Starting production FastAPI application server...
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## 5. Health Verification & Smoke Testing

### 1. Backend Health Check
```bash
curl -f https://${DOMAIN}/api/v1/health
```

Expected Response (`200 OK`):
```json
{
  "status": "healthy",
  "service": "GeM Bid Compliance Verification Platform",
  "version": "0.1.0",
  "database": "postgresql",
  "details": {
    "pgvector_extension": {
      "available": true,
      "version": "0.8.1"
    },
    "database_engine": "postgresql",
    "database_status": "HEALTHY"
  }
}
```

### 2. Mock Explorer Dataset Verification
```bash
curl -f https://${DOMAIN}/api/v1/mock-sources
```
Expected Response: 5,000 total records active across all 5 source registries.

---

## 6. Database Backup & Disaster Recovery

### Automated Backup via `pg_dump`
To take a complete, compressed binary snapshot of the PostgreSQL database without downtime:

```bash
docker exec -t gem_prod_db pg_dump -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-gem_compliance} -Fc -f /tmp/backup.dump
docker cp gem_prod_db:/tmp/backup.dump ./backups/gem_backup_$(date +%Y%m%d_%H%M%S).dump
docker exec -t gem_prod_db rm /tmp/backup.dump
```

### Database Restore via `pg_restore`
To restore from a previous dump file into a clean database:

```bash
# 1. Stop backend service to prevent write conflicts
docker compose -f docker/docker-compose.prod.yml stop backend

# 2. Restore database
docker cp ./backups/gem_backup_YYYYMMDD_HHMMSS.dump gem_prod_db:/tmp/restore.dump
docker exec -t gem_prod_db pg_restore -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-gem_compliance} --clean --if-exists /tmp/restore.dump
docker exec -t gem_prod_db rm /tmp/restore.dump

# 3. Restart backend
docker compose -f docker/docker-compose.prod.yml start backend
```

---

## 7. Rollback Procedure

If an update fails health checks or introduces an unexpected regression:

1. Revert Git repository to the previous stable release commit:
   ```bash
   git checkout <PREVIOUS_RELEASE_COMMIT_HASH>
   ```
2. Re-deploy the previous container images:
   ```bash
   docker compose -f docker/docker-compose.prod.yml --env-file .env.production up -d --build
   ```
3. If database schema was modified, restore the pre-update backup taken prior to deployment as detailed in Section 6.

---

## 8. Minimal Production Security Review

| Security Domain | Architecture Posture | Recommendation / Demo Mitigation |
|---|---|---|
| **Port Exposure** | Only Ports `80` and `443` are exposed on the host. PostgreSQL (`5432`), FastAPI (`8000`), and Next.js (`3000`) are isolated within `gem_prod_network`. | Verified. Host firewall (e.g. UFW) should allow only `80/tcp` and `443/tcp`. |
| **Secrets Management** | Zero secrets in Git or Dockerfiles. Credentials loaded strictly via `.env.production` (permissions `600`). | For cloud enterprise deployments, migrate `.env` to AWS Secrets Manager or HashiCorp Vault. |
| **CORS Configuration** | Single-domain architecture (`https://domain/api/*`) eliminates cross-origin browser requests. | Backend maintains explicit `BACKEND_CORS_ORIGINS` whitelist. |
| **API Key Exposure** | `NVIDIA_API_KEY` is present solely in backend memory/environment. Never exposed to browser or frontend. | Verified. No `NEXT_PUBLIC_` prefix on sensitive tokens. |
| **Upload Limits** | PyMuPDF extraction limits uploads to `50MB`. Caddy enforces `max_size 60MB`. | Protects backend against memory exhaustion from oversized PDF uploads. |
| **NVIDIA API Cost Risk** | Bounded context windows, max tokens clamped (`2048`), page-window chunking avoids unbounded prompt generation. | For public demo servers, place rate-limiting middleware (e.g. `slowapi` or Caddy `rate_limit`) on `/api/v1/tenders/upload`. |

---

## 9. Troubleshooting Common Issues

### Issue: Backend reports `RuntimeError: PostgreSQL is unavailable`
- **Cause**: PostgreSQL is not yet ready or credentials in `.env.production` do not match `POSTGRES_PASSWORD`.
- **Fix**: Check `docker compose logs postgres`. Ensure `ALLOW_SQLITE_FALLBACK=false` is maintained and verify DB credentials.

### Issue: Caddy reports TLS handshake failure on local demo
- **Cause**: Domain is set to `localhost` without trusting Caddy's root certificate.
- **Fix**: In demo environments, install Caddy root certificate via `docker exec -it gem_prod_proxy caddy trust` or access via `http://localhost` on port 80.
