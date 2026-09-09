#!/bin/sh
set -e

echo "=================================================================="
echo "SIH26100 GeM Compliance Platform — Production Backend Startup"
echo "=================================================================="

echo "==> Verifying database runtime..."
echo "    ALLOW_SQLITE_FALLBACK is set to: ${ALLOW_SQLITE_FALLBACK}"

if [ "${ALLOW_SQLITE_FALLBACK}" = "true" ]; then
    echo "WARNING: ALLOW_SQLITE_FALLBACK is true! In production this should be false."
fi

echo "==> Running idempotent mock seeder & database initialization..."
python -m app.services.mock_seeder

echo "==> Starting production FastAPI application server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
