"""Automated Test Suite for Phase 6 Mock Verification Data Explorer.

Covers tests 1 through 19:
1. Source list endpoint (/api/v1/mock-sources).
2. Correct source counts (1,000 each, 5,000 total).
3. Pagination behavior.
4. Maximum page size enforcement (>100 rejected).
5. GSTN search.
6. Udyam search.
7. MCA search.
8. Income Tax search.
9. MII search.
10. Status filtering.
11. Showcase bidder filtering.
12. Record detail retrieval.
13. Unknown source rejected (404).
14. Dataset integrity endpoint (/api/v1/mock-sources/integrity).
15. Integrity reports 5,000 total records.
16. Integrity confirms all records are mock with correct label.
17. Integrity confirms unique identifiers and verification IDs.
18. Integrity confirms showcase mappings (all 10 mapped).
19. Integrity confirms five required contradiction/exemption scenarios.
"""

import asyncio
import pytest
from starlette.testclient import TestClient
from app.main import app
from app.core import database as db_module
from app.services.mock_seeder import seed_mock_sources


@pytest.fixture(scope="module")
def client():
    # Ensure database tables and fallback are initialized
    async def _setup():
        await db_module.init_db()
        async with db_module.AsyncSessionLocal() as session:
            await seed_mock_sources(session)
    asyncio.run(_setup())

    with TestClient(app) as c:
        yield c


# 1. Source list endpoint
def test_mock_sources_list_endpoint(client):
    response = client.get("/api/v1/mock-sources")
    assert response.status_code == 200
    data = response.json()
    assert "sources" in data
    assert "gstn" in data["sources"]
    assert "udyam" in data["sources"]
    assert "mca" in data["sources"]
    assert "income_tax" in data["sources"]
    assert "mii" in data["sources"]


# 2. Correct source counts (1,000 each, 5,000 total)
def test_mock_sources_counts(client):
    response = client.get("/api/v1/mock-sources")
    assert response.status_code == 200
    data = response.json()
    assert data["total_records"] == 5000
    for key in ["gstn", "udyam", "mca", "income_tax", "mii"]:
        assert data["sources"][key]["count"] == 1000, f"Expected 1000 for {key}, got {data['sources'][key]['count']}"


# 3. Pagination behavior
def test_pagination_behavior(client):
    response = client.get("/api/v1/mock-sources/gstn?page=1&page_size=25")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 25
    assert data["total"] == 1000
    assert data["total_pages"] == 40
    assert len(data["items"]) == 25


# 4. Maximum page size enforcement (>100 rejected)
def test_max_page_size_enforcement(client):
    response = client.get("/api/v1/mock-sources/gstn?page=1&page_size=101")
    assert response.status_code == 400
    assert "page_size cannot exceed 100" in response.json()["detail"]


# 5. GSTN search
def test_gstn_search(client):
    # Search by known showcase GSTIN
    response = client.get("/api/v1/mock-sources/gstn?search=27AAACE1001A1Z1")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(it["gstin"] == "27AAACE1001A1Z1" for it in data["items"])

    # Search by legal name substring
    response2 = client.get("/api/v1/mock-sources/gstn?search=Enterprise Tech")
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["total"] >= 1


# 6. Udyam search
def test_udyam_search(client):
    response = client.get("/api/v1/mock-sources/udyam?search=UDYAM-MH-01-0010001")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["items"][0]["udyam_registration_number"] == "UDYAM-MH-01-0010001"


# 7. MCA search
def test_mca_search(client):
    response = client.get("/api/v1/mock-sources/mca?search=U72200MH2015PLC261001")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["items"][0]["cin"] == "U72200MH2015PLC261001"


# 8. Income Tax search
def test_income_tax_search(client):
    response = client.get("/api/v1/mock-sources/income_tax?search=AAACE1001A")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["items"][0]["pan"] == "AAACE1001A"


# 9. MII search
def test_mii_search(client):
    response = client.get("/api/v1/mock-sources/mii?search=BIDDER-01")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["items"][0]["entity_identifier"] == "BIDDER-01"


# 10. Status filtering
def test_status_filtering(client):
    response = client.get("/api/v1/mock-sources/gstn?status=ACTIVE&page_size=20")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    for it in data["items"]:
        assert it["status"] == "ACTIVE"


# 11. Showcase bidder filtering
def test_showcase_bidder_filtering(client):
    response = client.get("/api/v1/mock-sources/gstn?showcase_only=true")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 10
    showcase_ids = {f"BIDDER-{i:02d}" for i in range(1, 11)}
    for it in data["items"]:
        assert it["entity_identifier"] in showcase_ids


# 12. Record detail retrieval
def test_record_detail_retrieval(client):
    response = client.get("/api/v1/mock-sources/gstn/MOCK-GSTN-BIDDER-01")
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "GSTN"
    assert data["record"]["verification_id"] == "MOCK-GSTN-BIDDER-01"
    assert data["record"]["entity_identifier"] == "BIDDER-01"
    assert data["record"]["is_mock"] is True
    assert "SYNTHETIC / MOCK DATA" in data["disclaimer"]


# 13. Unknown source rejected (404)
def test_unknown_source_rejected(client):
    response = client.get("/api/v1/mock-sources/nonexistent_registry")
    assert response.status_code == 404
    assert "Unknown mock source registry" in response.json()["detail"]


# 14. Dataset integrity endpoint
def test_dataset_integrity_endpoint(client):
    response = client.get("/api/v1/mock-sources/integrity")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PASS"


# 15. Integrity reports 5,000 total records
def test_integrity_reports_5000_records(client):
    response = client.get("/api/v1/mock-sources/integrity")
    assert response.status_code == 200
    data = response.json()
    assert data["total_records"] == 5000


# 16. Integrity confirms all records are mock
def test_integrity_confirms_all_mock(client):
    response = client.get("/api/v1/mock-sources/integrity")
    assert response.status_code == 200
    data = response.json()
    assert data["all_records_mock"] is True
    assert data["all_labels_valid"] is True
    for src_key, s_data in data["sources"].items():
        assert s_data["all_mock"] is True
        assert s_data["source_type_label_valid"] is True


# 17. Integrity confirms unique identifiers
def test_integrity_confirms_unique_identifiers(client):
    response = client.get("/api/v1/mock-sources/integrity")
    assert response.status_code == 200
    data = response.json()
    for src_key, s_data in data["sources"].items():
        assert s_data["verification_ids_unique"] is True, f"Non-unique vids in {src_key}"
        assert s_data["primary_identifiers_unique"] is True, f"Non-unique primary IDs in {src_key}"


# 18. Integrity confirms showcase mappings
def test_integrity_confirms_showcase_mappings(client):
    response = client.get("/api/v1/mock-sources/integrity")
    assert response.status_code == 200
    data = response.json()
    assert data["showcase_mappings"]["total_mapped"] == 10
    assert data["showcase_mappings"]["all_sources_present"] is True


# 19. Integrity confirms five required scenarios
def test_integrity_confirms_five_scenarios(client):
    response = client.get("/api/v1/mock-sources/integrity")
    assert response.status_code == 200
    data = response.json()
    scenarios = data["demo_scenarios"]

    # Scenario 1: Turnover Contradiction
    assert scenarios["turnover_contradiction"]["present"] is True
    assert scenarios["turnover_contradiction"]["target_bidder"] == "BIDDER-10"
    assert scenarios["turnover_contradiction"]["verified_turnover_cr"] == 3.65

    # Scenario 2: MSE Exemption
    assert scenarios["mse_exemption"]["present"] is True
    assert scenarios["mse_exemption"]["target_bidder"] == "BIDDER-03"
    assert scenarios["mse_exemption"]["enterprise_type"] == "MICRO"

    # Scenario 3: Local Content Shortfall
    assert scenarios["local_content"]["present"] is True
    assert scenarios["local_content"]["target_bidder"] == "BIDDER-10"
    assert scenarios["local_content"]["verified_local_content_pct"] == 32.0

    # Scenario 4: Name Variation
    assert scenarios["name_variation"]["present"] is True
    assert scenarios["name_variation"]["target_bidder"] == "BIDDER-04"

    # Scenario 5: Inactive/Cancelled Status
    assert scenarios["inactive_cancelled_status"]["present"] is True
    assert scenarios["inactive_cancelled_status"]["target_bidder"] == "BIDDER-08"
