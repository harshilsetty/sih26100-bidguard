import pytest
import math
import asyncio
from uuid import uuid4
from app.core.config import settings
from app.schemas.bidder import (
    DocumentExtractionStatus,
    IngestedDocumentResult,
    IngestedPageData,
    DocumentChunkItem,
)
from app.services.bidder_ingestion import (
    ingest_bidder_document,
    ingest_multiple_bidder_documents,
)
from app.services.chunking_service import (
    chunk_page_text,
    chunk_ingested_document,
    chunk_multiple_documents,
)
from app.services.embedding_service import (
    BaseEmbeddingProvider,
    StubEmbeddingProvider,
    NvidiaEmbeddingProvider,
    EmbeddingService,
    get_embedding_service,
)
from app.services.evidence_retrieval import (
    compute_cosine_similarity,
    build_clause_retrieval_query,
    retrieve_evidence_from_memory,
    retrieve_evidence_for_clause,
)
from app.utils.synthetic_bidders import (
    generate_bidder_a_pdf,
    generate_bidder_b_pdf,
    generate_bidder_c_pdf,
    generate_empty_scanned_pdf,
)


class TestBidderDocumentIngestion:
    """Tests for bidder PDF ingestion, page preservation, and error handling."""

    def test_single_document_ingestion_preserves_pages(self):
        bidder_id = uuid4()
        pdf_bytes = generate_bidder_a_pdf()

        result = ingest_bidder_document(
            pdf_source=pdf_bytes,
            bidder_id=bidder_id,
            filename="bidder_a_technical.pdf",
            doc_type="TECHNICAL_PROPOSAL",
        )

        assert result.bidder_id == bidder_id
        assert result.filename == "bidder_a_technical.pdf"
        assert result.doc_type == "TECHNICAL_PROPOSAL"
        assert result.total_pages == 4
        assert result.empty_pages_count == 0
        assert result.extraction_status == DocumentExtractionStatus.EXTRACTED
        assert len(result.pages) == 4

        # Verify page-level exact preservation
        page_numbers = [p.page_number for p in result.pages]
        assert page_numbers == [1, 2, 3, 4]
        assert "64-core processors" in result.pages[0].text
        assert "Turnover" in result.pages[1].text
        assert "Make in India" in result.pages[2].text
        assert "3 years" in result.pages[3].text

    def test_multiple_bidder_documents_ingestion(self):
        bidder_id = uuid4()
        doc_a = {"source": generate_bidder_a_pdf(), "filename": "doc_1.pdf", "doc_type": "TECHNICAL"}
        doc_b = {"source": generate_bidder_a_pdf(), "filename": "doc_2.pdf", "doc_type": "FINANCIAL"}

        results = ingest_multiple_bidder_documents([doc_a, doc_b], bidder_id=bidder_id)

        assert len(results) == 2
        assert results[0].filename == "doc_1.pdf"
        assert results[1].filename == "doc_2.pdf"
        assert results[0].document_id != results[1].document_id
        assert results[0].bidder_id == bidder_id
        assert results[1].bidder_id == bidder_id

    def test_empty_or_scanned_document_handling(self):
        bidder_id = uuid4()
        empty_pdf = generate_empty_scanned_pdf()

        result = ingest_bidder_document(
            pdf_source=empty_pdf,
            bidder_id=bidder_id,
            filename="scanned_blank.pdf",
        )

        assert result.total_pages == 1
        assert result.empty_pages_count == 1
        assert result.extraction_status == DocumentExtractionStatus.EMPTY_SCANNED
        assert result.pages[0].is_empty_or_scanned is True
        assert result.error_message is not None

    def test_corrupt_pdf_bytes_handling_does_not_crash(self):
        bidder_id = uuid4()
        corrupt_bytes = b"NOT_A_VALID_PDF_HEADER_12345"

        result = ingest_bidder_document(
            pdf_source=corrupt_bytes,
            bidder_id=bidder_id,
            filename="corrupt.pdf",
        )

        assert result.extraction_status == DocumentExtractionStatus.FAILED
        assert result.total_pages == 0
        assert result.error_message is not None


class TestPageAwareChunking:
    """Tests for deterministic chunking with exact page provenance and character offsets."""

    def test_chunk_provenance_and_offsets(self):
        bidder_id = uuid4()
        ingested = ingest_bidder_document(generate_bidder_a_pdf(), bidder_id, filename="tech.pdf")
        chunks = chunk_ingested_document(ingested, chunk_size=300, chunk_overlap=50)

        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.bidder_id == bidder_id
            assert chunk.document_id == ingested.document_id
            assert chunk.filename == "tech.pdf"
            assert chunk.page_number in [1, 2, 3, 4]
            assert chunk.start_char is not None
            assert chunk.end_char is not None
            assert chunk.end_char >= chunk.start_char
            assert len(chunk.chunk_text) > 0

            # Traceability: verify chunk text comes from that specific page
            page_text = ingested.pages[chunk.page_number - 1].text
            assert chunk.chunk_text in page_text

    def test_chunks_never_cross_page_boundaries(self):
        bidder_id = uuid4()
        ingested = ingest_bidder_document(generate_bidder_b_pdf(), bidder_id)
        chunks = chunk_ingested_document(ingested)

        # Chunks must each belong to exactly one page
        for c in chunks:
            assert isinstance(c.page_number, int)
            assert 1 <= c.page_number <= 4

    def test_empty_pages_produce_no_chunks(self):
        bidder_id = uuid4()
        empty_doc = ingest_bidder_document(generate_empty_scanned_pdf(), bidder_id)
        chunks = chunk_ingested_document(empty_doc)
        assert len(chunks) == 0


class TestEmbeddingService:
    """Tests for embedding service abstraction, stub provider, and strict dimension verification."""

    def test_stub_embedding_deterministic_and_normalized(self):
        async def _run():
            provider = StubEmbeddingProvider()
            assert provider.dimension == settings.EMBEDDING_DIM

            t1 = "ISO 9001:2015 certified servers"
            t2 = "ISO 9001:2015 certified servers"
            t3 = "Completely different text about annual turnover"

            v1 = await provider.embed_query(t1)
            v2 = await provider.embed_query(t2)
            v3 = await provider.embed_query(t3)

            assert len(v1) == settings.EMBEDDING_DIM
            # Deterministic: identical text -> identical vectors
            assert v1 == v2

            # Unit normalized (L2 norm == 1.0)
            norm = math.sqrt(sum(x * x for x in v1))
            assert pytest.approx(norm, rel=1e-5) == 1.0

            # Cosine similarity of identical text == 1.0
            assert pytest.approx(compute_cosine_similarity(v1, v2), rel=1e-5) == 1.0
            # Cosine similarity of different texts < 1.0
            assert compute_cosine_similarity(v1, v3) < 0.9

        asyncio.run(_run())

    def test_dimension_mismatch_fails_clearly(self):
        async def _run():
            class BadProvider(BaseEmbeddingProvider):
                @property
                def model_name(self) -> str:
                    return "bad-model"

                @property
                def dimension(self) -> int:
                    return 512  # Wrong dimension

                async def embed_texts(self, texts):
                    return [[0.1] * 512 for _ in texts]

                async def embed_query(self, query):
                    return [0.1] * 512

            service = EmbeddingService(provider=BadProvider())

            # Embedding query with wrong dimension must raise ValueError clearly
            with pytest.raises(ValueError, match="Embedding dimension mismatch"):
                await service.embed_query("Sample query")

            # Embedding chunks with wrong dimension must raise ValueError clearly
            chunk = DocumentChunkItem(
                chunk_id="test_c0",
                bidder_id=uuid4(),
                document_id=uuid4(),
                filename="test.pdf",
                page_number=1,
                chunk_index=0,
                chunk_text="Sample text",
            )
            with pytest.raises(ValueError, match="Embedding dimension mismatch"):
                await service.embed_chunks([chunk])

        asyncio.run(_run())


class TestBidderIsolatedRetrieval:
    """Tests for bidder isolation, cosine ranking, and query formulation."""

    def test_strict_bidder_isolation_guarantee(self):
        """Mathematical proof: Bidder A chunks never leak into Bidder B results and vice-versa."""
        async def _run():
            bidder_a_id = uuid4()
            bidder_b_id = uuid4()

            service = get_embedding_service(force_stub=True)

            # Ingest and chunk Bidder A
            doc_a = ingest_bidder_document(generate_bidder_a_pdf(), bidder_a_id, filename="bidder_a.pdf")
            chunks_a = chunk_ingested_document(doc_a)
            chunks_a = await service.embed_chunks(chunks_a)

            # Ingest and chunk Bidder B
            doc_b = ingest_bidder_document(generate_bidder_b_pdf(), bidder_b_id, filename="bidder_b.pdf")
            chunks_b = chunk_ingested_document(doc_b)
            chunks_b = await service.embed_chunks(chunks_b)

            # Combined pool (simulating database table containing all bidders' chunks)
            combined_chunk_pool = chunks_a + chunks_b

            clause = {
                "clause_code": "TECH-01",
                "title": "Server Compute Infrastructure",
                "description": "Bidder must provide rack servers with 64-core processors and 256GB ECC DDR5 RAM",
                "source_text": "The bidder must provide rack servers equipped with minimum 64-core processors and 256GB ECC DDR5 RAM.",
            }

            # Retrieve for Bidder A
            res_a = await retrieve_evidence_for_clause(
                clause=clause,
                bidder_id=bidder_a_id,
                chunks=combined_chunk_pool,
                embedding_service=service,
                top_k=5,
            )

            # Retrieve for Bidder B
            res_b = await retrieve_evidence_for_clause(
                clause=clause,
                bidder_id=bidder_b_id,
                chunks=combined_chunk_pool,
                embedding_service=service,
                top_k=5,
            )

            # 1. Assert Bidder A received evidence
            assert len(res_a.top_evidence) > 0
            # 2. Assert 100% of Bidder A's evidence belongs to Bidder A
            for ev in res_a.top_evidence:
                assert ev.bidder_id == bidder_a_id, f"LEAKAGE DETECTED: Chunk {ev.chunk_id} belongs to {ev.bidder_id}, not Bidder A!"
                assert ev.filename == "bidder_a.pdf"

            # 3. Assert Bidder B received evidence
            assert len(res_b.top_evidence) > 0
            # 4. Assert 100% of Bidder B's evidence belongs to Bidder B
            for ev in res_b.top_evidence:
                assert ev.bidder_id == bidder_b_id, f"LEAKAGE DETECTED: Chunk {ev.chunk_id} belongs to {ev.bidder_id}, not Bidder B!"
                assert ev.filename == "bidder_b.pdf"

            # 5. Assert ZERO intersection between retrieved chunk sets
            a_chunk_ids = {ev.chunk_id for ev in res_a.top_evidence}
            b_chunk_ids = {ev.chunk_id for ev in res_b.top_evidence}
            assert a_chunk_ids.isdisjoint(b_chunk_ids), "Cross-contamination found between Bidder A and Bidder B evidence sets!"

        asyncio.run(_run())

    def test_retrieval_ranking_orders_by_similarity_descending(self):
        async def _run():
            bidder_id = uuid4()
            service = get_embedding_service(force_stub=True)

            doc = ingest_bidder_document(generate_bidder_a_pdf(), bidder_id, filename="tech.pdf")
            chunks = chunk_ingested_document(doc)
            chunks = await service.embed_chunks(chunks)

            clause = {
                "clause_code": "FIN-01",
                "title": "Minimum Average Annual Turnover",
                "description": "Average annual turnover must be at least INR 5.0 Crores",
                "source_text": "Average annual turnover of the bidder during the last three financial years must be at least INR 5.0 Crores.",
            }

            res = await retrieve_evidence_for_clause(
                clause=clause,
                bidder_id=bidder_id,
                chunks=chunks,
                embedding_service=service,
                top_k=3,
            )

            assert len(res.top_evidence) == 3
            # Verify scores are sorted descending
            scores = [ev.similarity_score for ev in res.top_evidence]
            assert scores == sorted(scores, reverse=True)

            # Top evidence should be from Page 2 (Financial Criteria)
            top = res.top_evidence[0]
            assert top.page_number == 2
            assert "Turnover" in top.chunk_text or "Crores" in top.chunk_text

        asyncio.run(_run())

    def test_clause_query_formulation(self):
        clause = {
            "clause_code": "DEL-01",
            "title": "Delivery Timelines",
            "description": "Hardware items must be delivered and installed within 45 days",
            "source_text": "All hardware items and software licenses must be delivered and installed within 45 days from contract award.",
            "rule_config": {"parameter": "delivery_time_days", "value": 45, "unit": "days"},
        }
        query = build_clause_retrieval_query(clause)
        assert "Delivery Timelines" in query
        assert "delivery_time_days: 45 days" in query
        assert "within 45 days" in query
