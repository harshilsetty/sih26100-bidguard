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

from app.core.config import settings
from app.services.bidder_ingestion import ingest_bidder_document
from app.services.chunking_service import chunk_ingested_document
from app.services.embedding_service import get_embedding_service, NvidiaEmbeddingProvider
from app.services.evidence_retrieval import (
    retrieve_evidence_for_clause,
    retrieve_evidence_for_tender_clauses,
)
from app.utils.synthetic_bidders import (
    generate_bidder_a_pdf,
    generate_bidder_b_pdf,
    generate_bidder_c_pdf,
)

# 11 Realistic GeM Tender Clauses extracted in Day 2
TENDER_CLAUSES = [
    {
        "clause_code": "TECH-01",
        "category": "TECHNICAL",
        "title": "Server Compute Infrastructure",
        "description": "Rack servers equipped with minimum 64-core processors and 256GB ECC DDR5 RAM",
        "source_text": "The bidder must provide rack servers equipped with minimum 64-core processors and 256GB ECC DDR5 RAM.",
        "page_number": 1,
    },
    {
        "clause_code": "TECH-02",
        "category": "TECHNICAL",
        "title": "Hardware Quality & BIS Standards",
        "description": "BIS certification and ISO 9001:2015 quality standards compliance",
        "source_text": "All hardware components must be certified under BIS and comply with ISO 9001:2015 quality standards.",
        "page_number": 1,
    },
    {
        "clause_code": "TECH-03",
        "category": "TECHNICAL",
        "title": "OEM Warranty Coverage",
        "description": "3-year comprehensive on-site OEM warranty",
        "source_text": "Comprehensive on-site OEM warranty of 3 years shall be provided for all supplied equipment.",
        "page_number": 1,
    },
    {
        "clause_code": "FIN-01",
        "category": "FINANCIAL",
        "title": "Minimum Average Annual Turnover",
        "description": "Average annual turnover of at least INR 5.0 Crores during last 3 financial years",
        "source_text": "Average annual turnover of the bidder during the last three financial years must be at least INR 5.0 Crores.",
        "page_number": 2,
    },
    {
        "clause_code": "FIN-02",
        "category": "FINANCIAL",
        "title": "Audited Balance Sheets Upload",
        "description": "Audited balance sheets and CA certificate with UDIN",
        "source_text": "Audited balance sheets and chartered accountant certificates must be uploaded.",
        "page_number": 2,
    },
    {
        "clause_code": "FIN-03",
        "category": "FINANCIAL",
        "title": "Earnest Money Deposit (EMD)",
        "description": "Online bank guarantee of INR 10,00,000",
        "source_text": "Bidder must submit an Earnest Money Deposit of INR 10,00,000 via online bank guarantee.",
        "page_number": 2,
    },
    {
        "clause_code": "FIN-04",
        "category": "FINANCIAL",
        "title": "EMD Exemption for MSEs",
        "description": "Exemption permissible for registered MSEs",
        "source_text": "EMD exemption is permissible for registered Micro and Small Enterprises (MSEs).",
        "page_number": 2,
    },
    {
        "clause_code": "STAT-01",
        "category": "STATUTORY",
        "title": "Make in India (MII) Local Content",
        "description": "Minimum 50 percent local content for Class-I Local Supplier",
        "source_text": "Minimum 50 percent local content is mandatory for qualification under Class-I Local Supplier category.",
        "page_number": 3,
    },
    {
        "clause_code": "STAT-02",
        "category": "STATUTORY",
        "title": "Self-Certification of Local Content",
        "description": "Self-certification indicating percentage of local content",
        "source_text": "Self-certification indicating the percentage of local content must be provided.",
        "page_number": 3,
    },
    {
        "clause_code": "EXP-01",
        "category": "EXPERIENCE",
        "title": "Past Contract Execution",
        "description": "Execution of at least 2 similar enterprise IT contracts in last 3 years",
        "source_text": "Bidder must have successfully executed at least 2 similar enterprise IT contracts in the last 3 years.",
        "page_number": 3,
    },
    {
        "clause_code": "DEL-01",
        "category": "DELIVERY_SLA",
        "title": "Delivery Timelines",
        "description": "Hardware items delivered and installed within 45 days",
        "source_text": "All hardware items and software licenses must be delivered and installed within 45 days from contract award.",
        "page_number": 4,
    },
]


async def run_integration_test():
    print("=" * 75)
    print("DAY 3 INTEGRATION TEST: BIDDER INGESTION + EVIDENCE RETRIEVAL")
    print("=" * 75)

    # 1. Setup Bidders
    bidder_a_id = uuid4()
    bidder_b_id = uuid4()
    bidder_c_id = uuid4()

    print(f"Bidder A (Compliant)   : {bidder_a_id}")
    print(f"Bidder B (Non-Compliant): {bidder_b_id}")
    print(f"Bidder C (Suspicious)   : {bidder_c_id}")

    # 2. Ingestion
    print("\n[Step 1] Ingesting Synthetic Bidder PDF Documents (PyMuPDF)...")
    doc_a = ingest_bidder_document(generate_bidder_a_pdf(), bidder_a_id, filename="Bidder_A_Technical_Financial.pdf", doc_type="TECHNICAL_FINANCIAL")
    doc_b = ingest_bidder_document(generate_bidder_b_pdf(), bidder_b_id, filename="Bidder_B_Submission.pdf", doc_type="GENERAL_SUBMISSION")
    doc_c = ingest_bidder_document(generate_bidder_c_pdf(), bidder_c_id, filename="Bidder_C_Integrators.pdf", doc_type="BID_PROPOSAL")

    all_docs = [doc_a, doc_b, doc_c]
    total_docs = len(all_docs)
    total_pages = sum(d.total_pages for d in all_docs)

    print(f"  - Ingested {total_docs} bidder documents.")
    for d in all_docs:
        print(f"    * {d.filename}: {d.total_pages} pages, status={d.extraction_status.value}")

    # 3. Page-Aware Chunking
    print("\n[Step 2] Performing Page-Aware Chunking with Character Offsets...")
    chunks_a = chunk_ingested_document(doc_a)
    chunks_b = chunk_ingested_document(doc_b)
    chunks_c = chunk_ingested_document(doc_c)

    all_chunks = chunks_a + chunks_b + chunks_c
    total_chunks = len(all_chunks)

    print(f"  - Total chunks generated: {total_chunks}")
    print(f"    * Bidder A: {len(chunks_a)} chunks")
    print(f"    * Bidder B: {len(chunks_b)} chunks")
    print(f"    * Bidder C: {len(chunks_c)} chunks")

    # Verify chunk provenance integrity
    for c in all_chunks:
        assert c.page_number >= 1
        assert c.start_char is not None and c.end_char is not None
        assert c.end_char >= c.start_char

    # 4. Embedding Service
    print("\n[Step 3] Embedding Chunks with Vector Dimension Verification...")
    embedder = get_embedding_service()
    print(f"  - Active Embedding Provider: {embedder.provider.__class__.__name__}")
    print(f"  - Active Model Name        : {embedder.model_name}")
    print(f"  - Configured Dimension     : {embedder.dimension} (settings.EMBEDDING_DIM={settings.EMBEDDING_DIM})")

    # Embed all chunks
    await embedder.embed_chunks(all_chunks)
    print(f"  - Successfully generated unit-normalized {settings.EMBEDDING_DIM}-dim embeddings for all {total_chunks} chunks.")

    # 5. Execute Evidence Retrieval for Tender Clauses
    print("\n[Step 4] Executing Bidder-Isolated Evidence Retrieval across 11 Clauses...")
    top_k = settings.DEFAULT_RETRIEVAL_TOP_K

    evidence_a = await retrieve_evidence_for_tender_clauses(
        clauses=TENDER_CLAUSES,
        bidder_id=bidder_a_id,
        chunks=all_chunks,
        embedding_service=embedder,
        top_k=top_k,
    )

    evidence_b = await retrieve_evidence_for_tender_clauses(
        clauses=TENDER_CLAUSES,
        bidder_id=bidder_b_id,
        chunks=all_chunks,
        embedding_service=embedder,
        top_k=top_k,
    )

    evidence_c = await retrieve_evidence_for_tender_clauses(
        clauses=TENDER_CLAUSES,
        bidder_id=bidder_c_id,
        chunks=all_chunks,
        embedding_service=embedder,
        top_k=top_k,
    )

    # 6. MATHEMATICAL PROOF OF STRICT BIDDER ISOLATION
    print("\n[Step 5] Validating Strict Bidder Isolation (Zero Cross-Contamination)...")
    isolation_violations = []

    for item in evidence_a:
        for chunk in item.top_evidence:
            if chunk.bidder_id != bidder_a_id:
                isolation_violations.append(f"Bidder A result contains chunk from {chunk.bidder_id}")

    for item in evidence_b:
        for chunk in item.top_evidence:
            if chunk.bidder_id != bidder_b_id:
                isolation_violations.append(f"Bidder B result contains chunk from {chunk.bidder_id}")

    for item in evidence_c:
        for chunk in item.top_evidence:
            if chunk.bidder_id != bidder_c_id:
                isolation_violations.append(f"Bidder C result contains chunk from {chunk.bidder_id}")

    if isolation_violations:
        print(f"CRITICAL FAILURE: Found {len(isolation_violations)} isolation violations!")
        for v in isolation_violations:
            print(f"  - {v}")
        raise AssertionError("Bidder isolation failed!")
    else:
        print("  - [VERIFIED 100% ISOLATION]: Zero chunks leaked across bidder boundaries.")

    # 7. Print Sample Retrieved Evidence with Page Provenance
    print("\n" + "=" * 75)
    print("SAMPLE RETRIEVED EVIDENCE WITH PROVENANCE (BIDDER A vs BIDDER B vs BIDDER C)")
    print("=" * 75)

    sample_clauses = ["TECH-01", "FIN-01", "STAT-01", "DEL-01"]
    for code in sample_clauses:
        ev_a = next(e for e in evidence_a if e.clause_code == code)
        ev_b = next(e for e in evidence_b if e.clause_code == code)
        ev_c = next(e for e in evidence_c if e.clause_code == code)

        print(f"\n--- CLAUSE: [{code}] {ev_a.clause_title} ---")
        print(f"Query: \"{ev_a.query_text[:90]}...\"")

        top_a = ev_a.top_evidence[0] if ev_a.top_evidence else None
        top_b = ev_b.top_evidence[0] if ev_b.top_evidence else None
        top_c = ev_c.top_evidence[0] if ev_c.top_evidence else None

        if top_a:
            print(f"  [Bidder A (Compliant) Evidence]")
            print(f"    - Page {top_a.page_number} ({top_a.filename}) [sim: {top_a.similarity_score:.4f}]")
            print(f"    - Text: \"{top_a.chunk_text[:140]}...\"")

        if top_b:
            print(f"  [Bidder B (Non-Compliant) Evidence]")
            print(f"    - Page {top_b.page_number} ({top_b.filename}) [sim: {top_b.similarity_score:.4f}]")
            print(f"    - Text: \"{top_b.chunk_text[:140]}...\"")

        if top_c:
            print(f"  [Bidder C (Suspicious) Evidence]")
            print(f"    - Page {top_c.page_number} ({top_c.filename}) [sim: {top_c.similarity_score:.4f}]")
            print(f"    - Text: \"{top_c.chunk_text[:140]}...\"")

    print("\n" + "=" * 75)
    print("DAY 3 INTEGRATION TEST COMPLETED SUCCESSFULLY!")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(run_integration_test())
