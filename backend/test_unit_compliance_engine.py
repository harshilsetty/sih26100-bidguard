import pytest
import asyncio
from uuid import uuid4
from app.schemas.clause import RuleType
from app.schemas.evaluation import ComplianceStatus, DeterministicRuleResult
from app.schemas.bidder import RetrievedEvidenceChunk
from app.services.deterministic_rules import (
    evaluate_numeric_min,
    evaluate_numeric_max,
    evaluate_document_required,
    evaluate_deterministic_rule,
)
from app.services.compliance_engine import (
    evaluate_clause_compliance,
    evaluate_bidder_compliance,
)


class TestDeterministicRuleEngine:
    """Tests for pure Python deterministic rule execution (no LLM in math)."""

    def test_numeric_min_satisfied(self):
        res = evaluate_numeric_min(actual=6.85, required=5.0, parameter="turnover", unit="Crores")
        assert res.passed is True
        assert res.margin == 1.85
        assert "meets/exceeds required minimum 5.0 Crores" in res.message

    def test_numeric_min_failed(self):
        res = evaluate_numeric_min(actual=2.1, required=5.0, parameter="turnover", unit="Crores")
        assert res.passed is False
        assert res.margin == -2.9
        assert "shortfall: -2.9 Crores" in res.message

    def test_numeric_max_satisfied(self):
        res = evaluate_numeric_max(actual=30.0, required=45.0, parameter="delivery_days", unit="days")
        assert res.passed is True
        assert res.margin == 15.0
        assert "within required ceiling 45.0 days" in res.message

    def test_numeric_max_failed(self):
        res = evaluate_numeric_max(actual=90.0, required=45.0, parameter="delivery_days", unit="days")
        assert res.passed is False
        assert res.margin == -45.0
        assert "exceeds allowed maximum ceiling 45.0 days" in res.message

    def test_document_required_found(self):
        res = evaluate_document_required(
            doc_parameter="audited_balance_sheet",
            evidence_text="Audited balance sheets with CA UDIN are submitted.",
            explicitly_found=True,
        )
        assert res.passed is True
        assert "confirmed present" in res.message

    def test_missing_numeric_value_fails_safely(self):
        res = evaluate_numeric_min(actual=None, required=5.0, parameter="turnover")
        assert res.passed is False
        assert res.actual_value is None
        assert "No measurable value extracted" in res.message

    def test_rule_dispatcher_numeric_min(self):
        rule_cfg = {"type": "NUMERIC_MIN", "parameter": "local_content", "value": 50, "unit": "%"}
        res = evaluate_deterministic_rule(rule_cfg, extracted_value=62)
        assert res.passed is True
        assert res.margin == 12.0

    def test_rule_dispatcher_numeric_max(self):
        rule_cfg = {"type": "NUMERIC_MAX", "parameter": "delivery_time_days", "value": 45, "unit": "days"}
        res = evaluate_deterministic_rule(rule_cfg, extracted_value=90)
        assert res.passed is False


class TestHybridComplianceSynthesizer:
    """Tests for hybrid decision hierarchy (PASS, FAIL, REVIEW)."""

    def test_compliant_evidence_yields_pass(self):
        async def _run():
            bidder_id = uuid4()
            clause = {
                "clause_code": "FIN-01",
                "title": "Minimum Average Annual Turnover",
                "is_mandatory": True,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "average_annual_turnover", "value": 5.0, "unit": "Crores"},
            }
            chunks = [
                RetrievedEvidenceChunk(
                    chunk_id="c1",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder_a.pdf",
                    page_number=2,
                    chunk_index=0,
                    chunk_text="Average annual turnover of Bidder A during the last three financial years is INR 6.85 Crores.",
                    similarity_score=0.85,
                )
            ]

            eval_res = await evaluate_clause_compliance(clause, bidder_id, chunks)
            assert eval_res.status == ComplianceStatus.PASS
            assert eval_res.confidence_score >= 0.90
            assert "COMPLIANT" in eval_res.reasoning
            assert eval_res.evidence_page_number == 2
            assert eval_res.contradiction_detected is False

        asyncio.run(_run())

    def test_numeric_shortfall_yields_fail(self):
        async def _run():
            bidder_id = uuid4()
            clause = {
                "clause_code": "FIN-01",
                "title": "Minimum Average Annual Turnover",
                "is_mandatory": True,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "average_annual_turnover", "value": 5.0, "unit": "Crores"},
            }
            chunks = [
                RetrievedEvidenceChunk(
                    chunk_id="c2",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder_b.pdf",
                    page_number=2,
                    chunk_index=0,
                    chunk_text="The average annual turnover of Bidder B over the preceding three financial years is INR 2.1 Crores only.",
                    similarity_score=0.82,
                )
            ]

            eval_res = await evaluate_clause_compliance(clause, bidder_id, chunks)
            assert eval_res.status == ComplianceStatus.FAIL
            assert "NON-COMPLIANT" in eval_res.reasoning
            assert eval_res.rule_result.passed is False

        asyncio.run(_run())

    def test_cross_chunk_contradiction_yields_review(self):
        """Contradictory claims across chunks must immediately divert to REVIEW."""
        async def _run():
            bidder_id = uuid4()
            clause = {
                "clause_code": "STAT-01",
                "title": "Make in India (MII) Preference",
                "is_mandatory": True,
                "rule_config": {"type": "PERCENT_MIN", "parameter": "local_content_percentage", "value": 50, "unit": "%"},
            }
            # Conflicting chunks from Bidder C
            chunks = [
                RetrievedEvidenceChunk(
                    chunk_id="c3_p1",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder_c.pdf",
                    page_number=1,
                    chunk_index=0,
                    chunk_text="Bidder C declares Class-I Local Supplier status with 55 percent domestic local content.",
                    similarity_score=0.80,
                ),
                RetrievedEvidenceChunk(
                    chunk_id="c3_p2",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder_c.pdf",
                    page_number=2,
                    chunk_index=1,
                    chunk_text="Actual domestic value addition and local content stands at 32 percent at factory gate.",
                    similarity_score=0.78,
                ),
            ]

            eval_res = await evaluate_clause_compliance(clause, bidder_id, chunks)
            assert eval_res.status == ComplianceStatus.REVIEW
            assert eval_res.contradiction_detected is True
            assert "CONTRADICTION DETECTED" in eval_res.reasoning
            assert eval_res.requires_human_confirmation is True

        asyncio.run(_run())

    def test_ambiguous_evidence_yields_review(self):
        """Pending or expired credentials must divert to REVIEW."""
        async def _run():
            bidder_id = uuid4()
            clause = {
                "clause_code": "TECH-02",
                "title": "Hardware Certification",
                "is_mandatory": True,
                "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "bis_and_iso_cert", "value": None},
            }
            chunks = [
                RetrievedEvidenceChunk(
                    chunk_id="c4",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder_b.pdf",
                    page_number=1,
                    chunk_index=0,
                    chunk_text="BIS registration is currently pending application. ISO 9001 certification expired in 2024.",
                    similarity_score=0.75,
                )
            ]

            eval_res = await evaluate_clause_compliance(clause, bidder_id, chunks)
            assert eval_res.status == ComplianceStatus.REVIEW
            assert "AMBIGUOUS / INSUFFICIENT EVIDENCE" in eval_res.reasoning
            assert eval_res.requires_human_confirmation is True

        asyncio.run(_run())


class TestOfficerDecisionBoundary:
    """Tests confirming final qualification remains a human procurement-officer decision."""

    def test_bidder_report_does_not_unilaterally_disqualify(self):
        async def _run():
            bidder_id = uuid4()
            clauses = [
                {
                    "clause_code": "FIN-01",
                    "title": "Turnover",
                    "is_mandatory": True,
                    "rule_config": {"type": "NUMERIC_MIN", "parameter": "turnover", "value": 5.0, "unit": "Crores"},
                }
            ]
            evidence_map = {
                "FIN-01": [
                    RetrievedEvidenceChunk(
                        chunk_id="c1",
                        bidder_id=bidder_id,
                        document_id=uuid4(),
                        filename="bidder_b.pdf",
                        page_number=2,
                        chunk_index=0,
                        chunk_text="Average annual turnover is INR 2.1 Crores only.",
                        similarity_score=0.85,
                    )
                ]
            }

            report = await evaluate_bidder_compliance(clauses, bidder_id, evidence_map)
            assert report.total_clauses == 1
            assert report.fail_count == 1
            assert report.pass_count == 0
            # Report must provide an advisory recommendation for officer review, NOT a terminal database change
            assert "Procurement officer review recommended" in report.officer_recommendation
            assert "Advisory:" in report.officer_recommendation

        asyncio.run(_run())


class TestClauseScopedContradictionIsolation:
    """Regression tests verifying contradiction detection is strictly scoped to clause parameters.

    Never allows an unrelated parameter contradiction to leak across clauses.
    """

    def test_local_content_contradiction_does_not_affect_tech01(self):
        async def _run():
            bidder_id = uuid4()
            clause_tech = {
                "clause_code": "TECH-01",
                "title": "Server Compute Infrastructure",
                "is_mandatory": True,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "cpu_cores", "value": 64, "unit": "cores"},
            }
            # Evidence contains: conflicting local content (55% vs 32%), and valid 64-core processor evidence
            chunks = [
                RetrievedEvidenceChunk(
                    chunk_id="c1",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder.pdf",
                    page_number=1,
                    chunk_index=0,
                    chunk_text="Section 1: Servers equipped with 64-core processors. Local content declared at 55 percent.",
                    similarity_score=0.85,
                ),
                RetrievedEvidenceChunk(
                    chunk_id="c2",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder.pdf",
                    page_number=2,
                    chunk_index=1,
                    chunk_text="Section 2: Bill of Materials confirms local content stands at 32 percent.",
                    similarity_score=0.80,
                ),
            ]

            eval_res = await evaluate_clause_compliance(clause_tech, bidder_id, chunks)
            assert eval_res.status == ComplianceStatus.PASS
            assert eval_res.contradiction_detected is False
            assert eval_res.rule_result.passed is True
            assert eval_res.rule_result.actual_value == 64.0

        asyncio.run(_run())

    def test_local_content_contradiction_does_not_affect_del01(self):
        async def _run():
            bidder_id = uuid4()
            clause_del = {
                "clause_code": "DEL-01",
                "title": "Delivery Timelines",
                "is_mandatory": True,
                "rule_config": {"type": "NUMERIC_MAX", "parameter": "delivery_time_days", "value": 45, "unit": "days"},
            }
            # Evidence contains: conflicting local content (55% vs 32%), and valid 30-day delivery
            chunks = [
                RetrievedEvidenceChunk(
                    chunk_id="c1",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder.pdf",
                    page_number=1,
                    chunk_index=0,
                    chunk_text="Delivery within 30 days from award. Local content declared as 55 percent.",
                    similarity_score=0.85,
                ),
                RetrievedEvidenceChunk(
                    chunk_id="c2",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder.pdf",
                    page_number=2,
                    chunk_index=1,
                    chunk_text="Factory gate local content stands at 32 percent.",
                    similarity_score=0.80,
                ),
            ]

            eval_res = await evaluate_clause_compliance(clause_del, bidder_id, chunks)
            assert eval_res.status == ComplianceStatus.PASS
            assert eval_res.contradiction_detected is False
            assert eval_res.rule_result.passed is True
            assert eval_res.rule_result.actual_value == 30.0

        asyncio.run(_run())

    def test_turnover_contradiction_does_not_affect_stat01(self):
        async def _run():
            bidder_id = uuid4()
            clause_stat = {
                "clause_code": "STAT-01",
                "title": "Make in India Local Content",
                "is_mandatory": True,
                "rule_config": {"type": "PERCENT_MIN", "parameter": "local_content_percentage", "value": 50, "unit": "%"},
            }
            # Evidence contains: conflicting turnover (8.0 Cr vs 3.65 Cr), and valid 62% local content
            chunks = [
                RetrievedEvidenceChunk(
                    chunk_id="c1",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder.pdf",
                    page_number=1,
                    chunk_index=0,
                    chunk_text="Turnover is INR 8.0 Crores. Class-I local content in offered servers is 62 percent.",
                    similarity_score=0.85,
                ),
                RetrievedEvidenceChunk(
                    chunk_id="c2",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder.pdf",
                    page_number=2,
                    chunk_index=1,
                    chunk_text="CA Certificate confirms actual turnover is INR 3.65 Crores.",
                    similarity_score=0.80,
                ),
            ]

            eval_res = await evaluate_clause_compliance(clause_stat, bidder_id, chunks)
            assert eval_res.status == ComplianceStatus.PASS
            assert eval_res.contradiction_detected is False
            assert eval_res.rule_result.passed is True
            assert eval_res.rule_result.actual_value == 62.0

        asyncio.run(_run())

    def test_cpu_contradiction_only_affects_cpu_clauses(self):
        async def _run():
            bidder_id = uuid4()
            clause_cpu = {
                "clause_code": "TECH-01",
                "title": "Compute Infrastructure",
                "is_mandatory": True,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "cpu_cores", "value": 64, "unit": "cores"},
            }
            clause_del = {
                "clause_code": "DEL-01",
                "title": "Delivery",
                "is_mandatory": True,
                "rule_config": {"type": "NUMERIC_MAX", "parameter": "delivery_time_days", "value": 45, "unit": "days"},
            }
            # Evidence has conflicting CPU cores (64-core vs 32-core), and 30 days delivery
            chunks = [
                RetrievedEvidenceChunk(
                    chunk_id="c1",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder.pdf",
                    page_number=1,
                    chunk_index=0,
                    chunk_text="Proposal 1 proposes 64-core processors. Delivery within 30 days.",
                    similarity_score=0.85,
                ),
                RetrievedEvidenceChunk(
                    chunk_id="c2",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder.pdf",
                    page_number=2,
                    chunk_index=1,
                    chunk_text="Datasheet states entry-level 32-core processors.",
                    similarity_score=0.80,
                ),
            ]

            # CPU clause MUST detect contradiction
            eval_cpu = await evaluate_clause_compliance(clause_cpu, bidder_id, chunks)
            assert eval_cpu.status == ComplianceStatus.REVIEW
            assert eval_cpu.contradiction_detected is True

            # Delivery clause MUST NOT be affected by CPU contradiction
            eval_del = await evaluate_clause_compliance(clause_del, bidder_id, chunks)
            assert eval_del.status == ComplianceStatus.PASS
            assert eval_del.contradiction_detected is False

        asyncio.run(_run())

    def test_delivery_contradiction_only_affects_delivery_clauses(self):
        async def _run():
            bidder_id = uuid4()
            clause_del = {
                "clause_code": "DEL-01",
                "title": "Delivery",
                "is_mandatory": True,
                "rule_config": {"type": "NUMERIC_MAX", "parameter": "delivery_time_days", "value": 45, "unit": "days"},
            }
            clause_cpu = {
                "clause_code": "TECH-01",
                "title": "Compute Infrastructure",
                "is_mandatory": True,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "cpu_cores", "value": 64, "unit": "cores"},
            }
            # Evidence has conflicting delivery days (30 days vs 90 days), and 64-core processors
            chunks = [
                RetrievedEvidenceChunk(
                    chunk_id="c1",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder.pdf",
                    page_number=1,
                    chunk_index=0,
                    chunk_text="Commercial proposal: delivery within 30 days. Equipped with 64-core processors.",
                    similarity_score=0.85,
                ),
                RetrievedEvidenceChunk(
                    chunk_id="c2",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder.pdf",
                    page_number=2,
                    chunk_index=1,
                    chunk_text="Import shipment schedule: delivery will require 90 days from award.",
                    similarity_score=0.80,
                ),
            ]

            # Delivery clause MUST detect contradiction
            eval_del = await evaluate_clause_compliance(clause_del, bidder_id, chunks)
            assert eval_del.status == ComplianceStatus.REVIEW
            assert eval_del.contradiction_detected is True

            # CPU clause MUST NOT be affected by delivery contradiction
            eval_cpu = await evaluate_clause_compliance(clause_cpu, bidder_id, chunks)
            assert eval_cpu.status == ComplianceStatus.PASS
            assert eval_cpu.contradiction_detected is False

        asyncio.run(_run())

    def test_contradiction_between_two_turnover_values_affects_fin01(self):
        async def _run():
            bidder_id = uuid4()
            clause = {
                "clause_code": "FIN-01",
                "title": "Annual Turnover",
                "is_mandatory": True,
                "rule_config": {"type": "NUMERIC_MIN", "parameter": "average_annual_turnover", "value": 5.0, "unit": "Crores"},
            }
            chunks = [
                RetrievedEvidenceChunk(
                    chunk_id="c1",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder.pdf",
                    page_number=3,
                    chunk_index=0,
                    chunk_text="Management self-attestation claims annual business turnover exceeding INR 8.0 Crores.",
                    similarity_score=0.85,
                ),
                RetrievedEvidenceChunk(
                    chunk_id="c2",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder.pdf",
                    page_number=4,
                    chunk_index=1,
                    chunk_text="CA Certificate UDIN 24109823 confirms actual 3-year average turnover of the firm is INR 3.65 Crores only.",
                    similarity_score=0.80,
                ),
            ]

            eval_res = await evaluate_clause_compliance(clause, bidder_id, chunks)
            assert eval_res.status == ComplianceStatus.REVIEW
            assert eval_res.contradiction_detected is True
            assert "CONTRADICTION DETECTED" in eval_res.reasoning
            assert "turnover" in eval_res.contradiction_details

        asyncio.run(_run())

    def test_contradiction_between_two_local_content_values_affects_stat01(self):
        async def _run():
            bidder_id = uuid4()
            clause = {
                "clause_code": "STAT-01",
                "title": "Make in India Local Content",
                "is_mandatory": True,
                "rule_config": {"type": "PERCENT_MIN", "parameter": "local_content_percentage", "value": 50, "unit": "%"},
            }
            chunks = [
                RetrievedEvidenceChunk(
                    chunk_id="c1",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder.pdf",
                    page_number=1,
                    chunk_index=0,
                    chunk_text="Bidder declares local content in offered compute servers is 55 percent.",
                    similarity_score=0.85,
                ),
                RetrievedEvidenceChunk(
                    chunk_id="c2",
                    bidder_id=bidder_id,
                    document_id=uuid4(),
                    filename="bidder.pdf",
                    page_number=2,
                    chunk_index=1,
                    chunk_text="Bill of materials breakdown shows actual local content stands at 32 percent.",
                    similarity_score=0.80,
                ),
            ]

            eval_res = await evaluate_clause_compliance(clause, bidder_id, chunks)
            assert eval_res.status == ComplianceStatus.REVIEW
            assert eval_res.contradiction_detected is True
            assert "CONTRADICTION DETECTED" in eval_res.reasoning
            assert "local_content_percent" in eval_res.contradiction_details

        asyncio.run(_run())
