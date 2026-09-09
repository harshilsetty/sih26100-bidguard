import sys
import asyncio
import os
from uuid import uuid4
from typing import Dict, Any, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from app.schemas.evaluation import ComplianceStatus
from app.services.bidder_ingestion import ingest_bidder_document
from app.services.chunking_service import chunk_ingested_document
from app.services.embedding_service import get_embedding_service
from app.services.evidence_retrieval import retrieve_evidence_for_tender_clauses
from app.services.compliance_engine import evaluate_bidder_compliance
from app.utils.synthetic_bidders import (
    generate_bidder_a_pdf,
    generate_bidder_b_pdf,
    generate_bidder_c_pdf,
)

# 11 Structured GeM Tender Clauses with deterministic rule_configs
TENDER_CLAUSES = [
    {
        "clause_code": "TECH-01",
        "category": "TECHNICAL",
        "title": "Server Compute Infrastructure",
        "description": "Rack servers equipped with minimum 64-core processors and 256GB ECC DDR5 RAM",
        "source_text": "The bidder must provide rack servers equipped with minimum 64-core processors and 256GB ECC DDR5 RAM.",
        "is_mandatory": True,
        "page_number": 1,
        "rule_config": {"type": "NUMERIC_MIN", "parameter": "cpu_cores", "value": 64, "unit": "cores"},
    },
    {
        "clause_code": "TECH-02",
        "category": "TECHNICAL",
        "title": "Hardware Quality & BIS Standards",
        "description": "BIS certification and ISO 9001:2015 quality standards compliance",
        "source_text": "All hardware components must be certified under BIS and comply with ISO 9001:2015 quality standards.",
        "is_mandatory": True,
        "page_number": 1,
        "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "bis_and_iso_cert", "value": None},
    },
    {
        "clause_code": "TECH-03",
        "category": "TECHNICAL",
        "title": "OEM Warranty Coverage",
        "description": "3-year comprehensive on-site OEM warranty",
        "source_text": "Comprehensive on-site OEM warranty of 3 years shall be provided for all supplied equipment.",
        "is_mandatory": True,
        "page_number": 1,
        "rule_config": {"type": "NUMERIC_MIN", "parameter": "warranty_years", "value": 3, "unit": "years"},
    },
    {
        "clause_code": "FIN-01",
        "category": "FINANCIAL",
        "title": "Minimum Average Annual Turnover",
        "description": "Average annual turnover of at least INR 5.0 Crores during last 3 financial years",
        "source_text": "Average annual turnover of the bidder during the last three financial years must be at least INR 5.0 Crores.",
        "is_mandatory": True,
        "page_number": 2,
        "rule_config": {"type": "NUMERIC_MIN", "parameter": "average_annual_turnover", "value": 5.0, "unit": "Crores"},
    },
    {
        "clause_code": "FIN-02",
        "category": "FINANCIAL",
        "title": "Audited Balance Sheets Upload",
        "description": "Audited balance sheets and CA certificate with UDIN",
        "source_text": "Audited balance sheets and chartered accountant certificates must be uploaded.",
        "is_mandatory": True,
        "page_number": 2,
        "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "audited_balance_sheets", "value": None},
    },
    {
        "clause_code": "FIN-03",
        "category": "FINANCIAL",
        "title": "Earnest Money Deposit (EMD)",
        "description": "Online bank guarantee of INR 10,00,000",
        "source_text": "Bidder must submit an Earnest Money Deposit of INR 10,00,000 via online bank guarantee.",
        "is_mandatory": True,
        "page_number": 2,
        "rule_config": {"type": "NUMERIC_MIN", "parameter": "emd_amount", "value": 1000000, "unit": "INR"},
    },
    {
        "clause_code": "FIN-04",
        "category": "FINANCIAL",
        "title": "EMD Exemption for MSEs",
        "description": "Exemption permissible for registered MSEs",
        "source_text": "EMD exemption is permissible for registered Micro and Small Enterprises (MSEs).",
        "is_mandatory": False,
        "page_number": 2,
        "rule_config": {"type": "CUSTOM", "parameter": "mse_exemption", "value": None},
    },
    {
        "clause_code": "STAT-01",
        "category": "STATUTORY",
        "title": "Make in India (MII) Local Content",
        "description": "Minimum 50 percent local content for Class-I Local Supplier",
        "source_text": "Minimum 50 percent local content is mandatory for qualification under Class-I Local Supplier category.",
        "is_mandatory": True,
        "page_number": 3,
        "rule_config": {"type": "PERCENT_MIN", "parameter": "local_content_percentage", "value": 50, "unit": "%"},
    },
    {
        "clause_code": "STAT-02",
        "category": "STATUTORY",
        "title": "Self-Certification of Local Content",
        "description": "Self-certification indicating percentage of local content",
        "source_text": "Self-certification indicating the percentage of local content must be provided.",
        "is_mandatory": True,
        "page_number": 3,
        "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "local_content_self_cert", "value": None},
    },
    {
        "clause_code": "EXP-01",
        "category": "EXPERIENCE",
        "title": "Past Contract Execution",
        "description": "Execution of at least 2 similar enterprise IT contracts in last 3 years",
        "source_text": "Bidder must have successfully executed at least 2 similar enterprise IT contracts in the last 3 years.",
        "is_mandatory": True,
        "page_number": 3,
        "rule_config": {"type": "NUMERIC_MIN", "parameter": "similar_contracts_count", "value": 2, "unit": "contracts"},
    },
    {
        "clause_code": "DEL-01",
        "category": "DELIVERY_SLA",
        "title": "Delivery Timelines",
        "description": "Hardware items delivered and installed within 45 days",
        "source_text": "All hardware items and software licenses must be delivered and installed within 45 days from contract award.",
        "is_mandatory": True,
        "page_number": 4,
        "rule_config": {"type": "NUMERIC_MAX", "parameter": "delivery_time_days", "value": 45, "unit": "days"},
    },
]


async def run_integration_test():
    print("=" * 80)
    print("DAY 4 INTEGRATION TEST: HYBRID COMPLIANCE ENGINE")
    print("=" * 80)

    # 1. Setup Bidders
    bidder_a_id = uuid4()
    bidder_b_id = uuid4()
    bidder_c_id = uuid4()

    print(f"Bidder A (Compliant Enterprise)        : {bidder_a_id}")
    print(f"Bidder B (Non-Compliant Bidder)        : {bidder_b_id}")
    print(f"Bidder C (Contradictory / Suspicious)  : {bidder_c_id}")

    # 2. Ingest and Chunk
    print("\n[Step 1] Ingesting and Chunking Synthetic Bidder PDFs...")
    doc_a = ingest_bidder_document(generate_bidder_a_pdf(), bidder_a_id, filename="Bidder_A.pdf")
    doc_b = ingest_bidder_document(generate_bidder_b_pdf(), bidder_b_id, filename="Bidder_B.pdf")
    doc_c = ingest_bidder_document(generate_bidder_c_pdf(), bidder_c_id, filename="Bidder_C.pdf")

    chunks_a = chunk_ingested_document(doc_a)
    chunks_b = chunk_ingested_document(doc_b)
    chunks_c = chunk_ingested_document(doc_c)
    all_chunks = chunks_a + chunks_b + chunks_c

    # 3. Embed Chunks
    print("\n[Step 2] Generating Embeddings via Embedding Service...")
    embedder = get_embedding_service()
    await embedder.embed_chunks(all_chunks)
    print(f"  - Successfully embedded {len(all_chunks)} chunks across 3 bidders.")

    # 4. Retrieve Evidence
    print("\n[Step 3] Retrieving Evidence Chunks with Strict Bidder Isolation...")
    ev_a_list = await retrieve_evidence_for_tender_clauses(TENDER_CLAUSES, bidder_a_id, all_chunks, embedding_service=embedder)
    ev_b_list = await retrieve_evidence_for_tender_clauses(TENDER_CLAUSES, bidder_b_id, all_chunks, embedding_service=embedder)
    ev_c_list = await retrieve_evidence_for_tender_clauses(TENDER_CLAUSES, bidder_c_id, all_chunks, embedding_service=embedder)

    map_a = {item.clause_code: item.top_evidence for item in ev_a_list}
    map_b = {item.clause_code: item.top_evidence for item in ev_b_list}
    map_c = {item.clause_code: item.top_evidence for item in ev_c_list}

    # 5. Execute Hybrid Compliance Evaluation
    print("\n[Step 4] Executing Hybrid Compliance Engine across all 11 Clauses...")
    report_a = await evaluate_bidder_compliance(TENDER_CLAUSES, bidder_a_id, map_a)
    report_b = await evaluate_bidder_compliance(TENDER_CLAUSES, bidder_b_id, map_b)
    report_c = await evaluate_bidder_compliance(TENDER_CLAUSES, bidder_c_id, map_c)

    # 6. Verify Exact Decision Principles
    print("\n[Step 5] Verifying Hybrid Compliance Decisions...")

    # Bidder A verification: 0 FAIL, predominantly PASS
    print(f"  - Bidder A Summary: {report_a.pass_count} PASS, {report_a.fail_count} FAIL, {report_a.review_count} REVIEW")
    assert report_a.fail_count == 0, f"Bidder A should have 0 failures, got {report_a.fail_count}"
    assert report_a.pass_count >= 9, f"Bidder A should pass >= 9 criteria, got {report_a.pass_count}"

    # Bidder B verification: Multiple critical FAILS (Turnover, Delivery, Cores, Warranty, Local Content)
    print(f"  - Bidder B Summary: {report_b.pass_count} PASS, {report_b.fail_count} FAIL, {report_b.review_count} REVIEW")
    assert report_b.fail_count >= 5, f"Bidder B should fail >= 5 criteria, got {report_b.fail_count}"

    # Verify specific deterministic rule failures on Bidder B
    b_tech01 = next(e for e in report_b.evaluations if e.clause_code == "TECH-01")
    assert b_tech01.status == ComplianceStatus.FAIL
    assert b_tech01.claimed_value == "32.0 cores"
    assert b_tech01.rule_result.actual_value == 32.0
    assert b_tech01.rule_result.required_value == 64.0
    assert "shortfall" in b_tech01.rule_result.message

    b_fin01 = next(e for e in report_b.evaluations if e.clause_code == "FIN-01")
    assert b_fin01.status == ComplianceStatus.FAIL
    assert b_fin01.rule_result.passed is False
    assert "shortfall" in b_fin01.rule_result.message

    b_del01 = next(e for e in report_b.evaluations if e.clause_code == "DEL-01")
    assert b_del01.status == ComplianceStatus.FAIL
    assert b_del01.rule_result.passed is False
    assert "exceeds" in b_del01.rule_result.message

    # Bidder C verification: Isolated REVIEW decisions triggered strictly by matching parameter contradictions
    print(f"  - Bidder C Summary: {report_c.pass_count} PASS, {report_c.fail_count} FAIL, {report_c.review_count} REVIEW")
    assert report_c.review_count < 11, f"Bidder C should not be 11 reviews, got {report_c.review_count}"
    assert report_c.review_count >= 2, f"Bidder C should have >= 2 review items from contradictions, got {report_c.review_count}"
    assert report_c.fail_count >= 3, f"Bidder C should have failures on missing criteria, got {report_c.fail_count}"

    # Confirm TECH-01 and DEL-01 in Bidder C did NOT leak contradiction
    c_tech01 = next(e for e in report_c.evaluations if e.clause_code == "TECH-01")
    assert c_tech01.status == ComplianceStatus.FAIL
    assert c_tech01.contradiction_detected is False

    c_del01 = next(e for e in report_c.evaluations if e.clause_code == "DEL-01")
    assert c_del01.status == ComplianceStatus.FAIL
    assert c_del01.contradiction_detected is False

    # Confirm parameter-specific contradictions in Bidder C
    c_stat01 = next(e for e in report_c.evaluations if e.clause_code == "STAT-01")
    assert c_stat01.status == ComplianceStatus.REVIEW
    assert c_stat01.contradiction_detected is True
    assert "local_content_percent" in c_stat01.contradiction_details

    c_fin01 = next(e for e in report_c.evaluations if e.clause_code == "FIN-01")
    assert c_fin01.status == ComplianceStatus.REVIEW
    assert c_fin01.contradiction_detected is True
    assert "turnover" in c_fin01.contradiction_details

    print("  - [DECISION PRINCIPLES VERIFIED]: All 3 test profiles behaved strictly according to specification.")

    # 7. Print Full Audit Trail Table
    print("\n" + "=" * 80)
    print("HYBRID COMPLIANCE ENGINE AUDIT TRAIL (ALL 11 CLAUSES)")
    print("=" * 80)

    for tc in TENDER_CLAUSES:
        code = tc["clause_code"]
        ea = next(e for e in report_a.evaluations if e.clause_code == code)
        eb = next(e for e in report_b.evaluations if e.clause_code == code)
        ec = next(e for e in report_c.evaluations if e.clause_code == code)

        print(f"\n[CLAUSE {code}] {ea.clause_title}")
        print(f"  * Bidder A: [{ea.status.value}] Claim: '{ea.claimed_value}' | Page {ea.evidence_page_number} | {ea.reasoning[:90]}...")
        print(f"  * Bidder B: [{eb.status.value}] Claim: '{eb.claimed_value}' | Page {eb.evidence_page_number} | {eb.reasoning[:90]}...")
        print(f"  * Bidder C: [{ec.status.value}] Claim: '{ec.claimed_value}' | Page {ec.evidence_page_number} | {ec.reasoning[:90]}...")

    print("\n" + "=" * 80)
    print("PROCUREMENT OFFICER RECOMMENDATIONS:")
    print("=" * 80)
    print(f"  * Bidder A: {report_a.officer_recommendation}")
    print(f"  * Bidder B: {report_b.officer_recommendation}")
    print(f"  * Bidder C: {report_c.officer_recommendation}")
    print("\n" + "=" * 80)
    print("DAY 4 INTEGRATION TEST COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_integration_test())
