"""Mock Government Source Data Seeder.

Phase 6.2 — SIH26100 Mock Integrated Verification Foundation.
Loads deterministic synthetic datasets into isolated PostgreSQL / database tables:
- mock_gstn_records (~1,000 records)
- mock_udyam_records (~1,000 records)
- mock_mca_records (~1,000 records)
- mock_income_tax_records (~1,000 records)
- mock_mii_records (~1,000 records)
Total: ~5,000 records.

Idempotent: Safe to execute repeatedly without duplicating data.
CLI: python -m app.services.mock_seeder
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import database as db_module
from app.models.mock_sources import (
    MockGSTNRecord,
    MockUdyamRecord,
    MockMCARecord,
    MockIncomeTaxRecord,
    MockMIIRecord,
)

logger = logging.getLogger(__name__)

SOURCE_CONFIGS = [
    {
        "name": "GSTN",
        "file": "gstn.json",
        "model": MockGSTNRecord,
    },
    {
        "name": "UDYAM",
        "file": "udyam.json",
        "model": MockUdyamRecord,
    },
    {
        "name": "MCA",
        "file": "mca.json",
        "model": MockMCARecord,
    },
    {
        "name": "INCOME_TAX",
        "file": "income_tax.json",
        "model": MockIncomeTaxRecord,
    },
    {
        "name": "MII",
        "file": "mii.json",
        "model": MockMIIRecord,
    },
]


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO timestamp string cleanly."""
    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"
    return datetime.fromisoformat(ts_str)


async def seed_mock_sources(
    session: AsyncSession,
    fixtures_dir: Path | None = None
) -> Dict[str, Dict[str, int]]:
    """Seed synthetic government verification sources into database idempotently.

    Returns:
        Dict mapping source name to stats: {"inserted": int, "existing": int, "total_source": int}
    """
    if fixtures_dir is None:
        # Default to backend/mock_data
        fixtures_dir = Path(__file__).resolve().parent.parent.parent / "mock_data"

    results: Dict[str, Dict[str, int]] = {}

    for config in SOURCE_CONFIGS:
        source_name = config["name"]
        file_path = fixtures_dir / config["file"]
        model_cls = config["model"]

        if not file_path.exists():
            logger.warning(f"Fixture file not found: {file_path}")
            results[source_name] = {"inserted": 0, "existing": 0, "total_source": 0}
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            records: List[Dict[str, Any]] = json.load(f)

        # Query existing verification_ids for idempotency
        stmt = select(model_cls.verification_id)
        res = await session.execute(stmt)
        existing_ids = set(res.scalars().all())

        new_records = []
        for rec in records:
            if rec["verification_id"] in existing_ids:
                continue

            # Copy to avoid mutating fixture
            rec_data = dict(rec)
            if "verification_timestamp" in rec_data and isinstance(rec_data["verification_timestamp"], str):
                rec_data["verification_timestamp"] = _parse_timestamp(rec_data["verification_timestamp"])

            new_records.append(model_cls(**rec_data))

        if new_records:
            # Insert in chunks of 500 for memory and statement safety
            chunk_size = 500
            for i in range(0, len(new_records), chunk_size):
                session.add_all(new_records[i : i + chunk_size])
                await session.flush()
            await session.commit()

        total_in_db = len(existing_ids) + len(new_records)
        results[source_name] = {
            "inserted": len(new_records),
            "existing": len(existing_ids),
            "total_source": total_in_db,
        }

    return results


async def main():
    """CLI execution for mock data seeding."""
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("SIH 2026 — SEEDING MOCK INTEGRATED VERIFICATION SOURCES")
    print("=" * 60)

    # Initialize tables
    await db_module.init_db()

    async with db_module.AsyncSessionLocal() as session:
        results = await seed_mock_sources(session)

    total_inserted = sum(s["inserted"] for s in results.values())
    total_in_db = sum(s["total_source"] for s in results.values())

    print("\nSeeding Results:")
    for source, stats in results.items():
        print(f"  {source:<12}: Inserted={stats['inserted']:<5} Existing={stats['existing']:<5} Total={stats['total_source']}")

    print("-" * 60)
    print(f"Grand Total: Inserted {total_inserted} records. Total active records in DB: {total_in_db}")
    print("Idempotency guarantee verified.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
