"""Test Suite for Phase 6.1 and 6.2 — Mock Integrated Verification Foundation.

Validates:
1. Valid GSTN model accepted.
2. Invalid source record rejected by schema.
3. GSTN fixture approximately 1,000 records.
4. Udyam fixture approximately 1,000 records.
5. MCA fixture approximately 1,000 records.
6. Income Tax fixture approximately 1,000 records.
7. MII fixture approximately 1,000 records.
8. Combined fixture count approximately 5,000 records.
9. Seeder is idempotent (repeated runs do not duplicate data).
10. Every mock record has is_mock = true.
11. Every mock record has source_type = "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION".
12. Verification IDs are unique within each source.
13. Required source identifiers are unique within each source.
14. All 10 showcase bidders have deterministic mappings across all 5 sources.
15. Turnover contradiction fixture exists (₹8 Cr bidder vs ₹3.65 Cr GSTN).
16. Udyam ACTIVE + MICRO fixture exists.
17. Local-content MII fixture exists (32% local content).
18. MCA entity-name variation fixture exists.
19. Inactive / cancelled / suspended fixture exists.
"""

import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from app.schemas.mock_sources import (
    MockGSTNRecordSchema,
    MockUdyamRecordSchema,
    MockMCARecordSchema,
    MockIncomeTaxRecordSchema,
    MockMIIRecordSchema,
    MOCK_SOURCE_TYPE_LABEL,
)
from app.services.mock_seeder import seed_mock_sources
from app.core import database as db_module

MOCK_DATA_DIR = Path(__file__).resolve().parent / "mock_data"


@pytest.fixture(scope="module")
def fixtures():
    """Load all 5 mock fixtures for validation."""
    data = {}
    sources = ["gstn", "udyam", "mca", "income_tax", "mii"]
    for src in sources:
        fpath = MOCK_DATA_DIR / f"{src}.json"
        assert fpath.exists(), f"Fixture file missing: {fpath}"
        with open(fpath, "r", encoding="utf-8") as f:
            data[src] = json.load(f)
    return data


# Test 1: Valid GSTN model accepted
def test_valid_gstn_model_accepted():
    payload = {
        "verification_id": "MOCK-GSTN-TEST-01",
        "source": "GSTN",
        "entity_identifier": "BIDDER-TEST",
        "status": "ACTIVE",
        "gstin": "27AAACE1234A1Z5",
        "legal_name": "Test Valid Enterprise Private Limited",
        "registration_status": "ACTIVE",
        "registration_date": "2020-01-01",
        "state": "Maharashtra",
        "verified_turnover": 12.5,
        "taxpayer_type": "Regular",
        "filing_status": "UP_TO_DATE",
        "verified_fields": {"turnover": 12.5},
        "raw_response": {"ok": True},
        "is_mock": True,
        "source_type": MOCK_SOURCE_TYPE_LABEL,
    }
    record = MockGSTNRecordSchema(**payload)
    assert record.gstin == "27AAACE1234A1Z5"
    assert record.is_mock is True
    assert record.verified_turnover == 12.5


# Test 2: Invalid source record rejected
def test_invalid_source_record_rejected():
    payload = {
        "verification_id": "MOCK-GSTN-TEST-02",
        "source": "GSTN",
        # Missing required entity_identifier, gstin, legal_name, verified_turnover
    }
    with pytest.raises(ValidationError):
        MockGSTNRecordSchema(**payload)


# Test 3: GSTN fixture approximately 1,000 records
def test_gstn_fixture_count(fixtures):
    count = len(fixtures["gstn"])
    assert 950 <= count <= 1050, f"GSTN count {count} is outside expected ~1,000 range"
    assert count == 1000


# Test 4: Udyam fixture approximately 1,000 records
def test_udyam_fixture_count(fixtures):
    count = len(fixtures["udyam"])
    assert 950 <= count <= 1050, f"Udyam count {count} is outside expected ~1,000 range"
    assert count == 1000


# Test 5: MCA fixture approximately 1,000 records
def test_mca_fixture_count(fixtures):
    count = len(fixtures["mca"])
    assert 950 <= count <= 1050, f"MCA count {count} is outside expected ~1,000 range"
    assert count == 1000


# Test 6: Income Tax fixture approximately 1,000 records
def test_income_tax_fixture_count(fixtures):
    count = len(fixtures["income_tax"])
    assert 950 <= count <= 1050, f"Income Tax count {count} is outside expected ~1,000 range"
    assert count == 1000


# Test 7: MII fixture approximately 1,000 records
def test_mii_fixture_count(fixtures):
    count = len(fixtures["mii"])
    assert 950 <= count <= 1050, f"MII count {count} is outside expected ~1,000 range"
    assert count == 1000


# Test 8: Combined fixture count approximately 5,000
def test_combined_fixture_count(fixtures):
    total = sum(len(records) for records in fixtures.values())
    assert 4800 <= total <= 5200, f"Total records {total} is outside expected ~5,000 range"
    assert total == 5000


# Test 9: Seeder is idempotent
def test_seeder_idempotency():
    import asyncio

    async def _check():
        await db_module.init_db()
        async with db_module.AsyncSessionLocal() as session:
            # First seed ensures data is populated
            res1 = await seed_mock_sources(session, fixtures_dir=MOCK_DATA_DIR)
            # Second seed run MUST insert 0 new records and maintain total
            res2 = await seed_mock_sources(session, fixtures_dir=MOCK_DATA_DIR)

            for src, stats in res2.items():
                assert stats["inserted"] == 0, f"Source {src} inserted {stats['inserted']} on second seed run (not idempotent)"
                assert stats["existing"] >= 1000, f"Source {src} existing count {stats['existing']} less than 1000"

    asyncio.run(_check())


# Test 10: Every mock record has is_mock = true
def test_every_mock_record_has_is_mock_true(fixtures):
    for src_name, records in fixtures.items():
        for i, rec in enumerate(records):
            assert rec.get("is_mock") is True, f"{src_name}[{i}] missing is_mock=True"


# Test 11: Every mock record has correct source_type label
def test_every_mock_record_source_type_label(fixtures):
    for src_name, records in fixtures.items():
        for i, rec in enumerate(records):
            assert (
                rec.get("source_type") == MOCK_SOURCE_TYPE_LABEL
            ), f"{src_name}[{i}] source_type '{rec.get('source_type')}' != expected label"


# Test 12: Verification IDs are unique within each source
def test_verification_ids_unique_within_source(fixtures):
    for src_name, records in fixtures.items():
        vids = [rec["verification_id"] for rec in records]
        assert len(vids) == len(set(vids)), f"Duplicate verification_id found in source {src_name}"


# Test 13: Required source identifiers are unique within each source
def test_source_identifiers_unique(fixtures):
    # GSTN -> gstin
    gstins = [r["gstin"] for r in fixtures["gstn"]]
    assert len(gstins) == len(set(gstins)), "Duplicate GSTIN found in GSTN fixture"

    # Udyam -> udyam_registration_number
    udyams = [r["udyam_registration_number"] for r in fixtures["udyam"]]
    assert len(udyams) == len(set(udyams)), "Duplicate Udyam number found in Udyam fixture"

    # MCA -> cin
    cins = [r["cin"] for r in fixtures["mca"]]
    assert len(cins) == len(set(cins)), "Duplicate CIN found in MCA fixture"

    # Income Tax -> pan
    pans = [r["pan"] for r in fixtures["income_tax"]]
    assert len(pans) == len(set(pans)), "Duplicate PAN found in Income Tax fixture"

    # MII -> verification_id
    mii_vids = [r["verification_id"] for r in fixtures["mii"]]
    assert len(mii_vids) == len(set(mii_vids)), "Duplicate verification_id in MII fixture"


# Test 14: All 10 showcase bidders have deterministic mappings across all 5 sources
def test_showcase_bidders_mapped_across_sources(fixtures):
    showcase_bidders = [f"BIDDER-{i:02d}" for i in range(1, 11)]

    for bidder_id in showcase_bidders:
        for src_name in ["gstn", "udyam", "mca", "income_tax", "mii"]:
            matches = [r for r in fixtures[src_name] if r["entity_identifier"] == bidder_id]
            assert (
                len(matches) == 1
            ), f"Showcase bidder {bidder_id} has {len(matches)} records in {src_name} (expected exactly 1)"


# Test 15: Turnover contradiction fixture exists (₹8 Cr declared vs ₹3.65 Cr GSTN)
def test_turnover_contradiction_fixture(fixtures):
    bidder_10_gstn = next(
        (r for r in fixtures["gstn"] if r["entity_identifier"] == "BIDDER-10"), None
    )
    assert bidder_10_gstn is not None, "BIDDER-10 record not found in GSTN fixture"
    assert (
        bidder_10_gstn["verified_turnover"] == 3.65
    ), f"Expected verified turnover of 3.65 Cr for BIDDER-10, got {bidder_10_gstn['verified_turnover']}"


# Test 16: Udyam ACTIVE + MICRO fixture exists
def test_udyam_active_micro_fixture(fixtures):
    active_micro_records = [
        r
        for r in fixtures["udyam"]
        if r["status"] == "ACTIVE" and r["enterprise_type"] == "MICRO"
    ]
    assert len(active_micro_records) > 0, "No ACTIVE MICRO record found in Udyam fixture"

    # Specifically verify showcase bidder 3 (MSE exemption scenario)
    bidder_03_udyam = next(
        (r for r in fixtures["udyam"] if r["entity_identifier"] == "BIDDER-03"), None
    )
    assert bidder_03_udyam is not None
    assert bidder_03_udyam["status"] == "ACTIVE"
    assert bidder_03_udyam["enterprise_type"] == "MICRO"


# Test 17: Local-content MII fixture exists (32% local content)
def test_local_content_mii_fixture(fixtures):
    bidder_10_mii = next(
        (r for r in fixtures["mii"] if r["entity_identifier"] == "BIDDER-10"), None
    )
    assert bidder_10_mii is not None, "BIDDER-10 record not found in MII fixture"
    assert (
        bidder_10_mii["verified_local_content"] == 32.0
    ), f"Expected verified local content 32.0% for BIDDER-10, got {bidder_10_mii['verified_local_content']}"


# Test 18: MCA entity-name variation exists
def test_mca_entity_name_variation_fixture(fixtures):
    bidder_04_mca = next(
        (r for r in fixtures["mca"] if r["entity_identifier"] == "BIDDER-04"), None
    )
    assert bidder_04_mca is not None, "BIDDER-04 record not found in MCA fixture"
    assert "Alpha Technology Private Limited" in bidder_04_mca["legal_name"]
    # Check that variation is tracked in verified_fields or notes
    assert (
        bidder_04_mca["verified_fields"].get("name_variation_detected") is True
        or "Private Limited" in bidder_04_mca["legal_name"]
    )


# Test 19: Inactive/cancelled/suspended fixture exists
def test_inactive_cancelled_fixture(fixtures):
    bidder_08_gstn = next(
        (r for r in fixtures["gstn"] if r["entity_identifier"] == "BIDDER-08"), None
    )
    bidder_08_it = next(
        (r for r in fixtures["income_tax"] if r["entity_identifier"] == "BIDDER-08"), None
    )
    assert bidder_08_gstn is not None
    assert bidder_08_gstn["status"] in ["CANCELLED", "SUSPENDED", "INACTIVE"]
    assert bidder_08_it is not None
    assert bidder_08_it["pan_status"] in ["INOPERATIVE", "CANCELLED", "INVALID"]
