import unittest
import pymupdf
import asyncio
from unittest.mock import patch, AsyncMock
from pydantic import ValidationError

from app.schemas.clause import (
    ClauseCategory,
    MandatoryStatus,
    RuleType,
    DraftRuleConfig,
    ExtractedClauseItem,
    ExtractedRawClause,
    LLMExtractionBatch,
)
from app.services.pdf_extractor import extract_pages_from_pdf
from app.services.clause_extractor import (
    build_page_windows,
    format_window_text,
    verify_source_text_presence,
    normalize_title,
    deduplicate_clauses,
    assign_clause_codes,
    process_window_with_degradation,
    extract_clauses_from_tender_pages,
)


class TestClauseExtractionSchemas(unittest.TestCase):
    def test_extracted_clause_item_valid(self):
        item = ExtractedClauseItem(
            category=ClauseCategory.FINANCIAL,
            title="Minimum Annual Turnover",
            description="The bidder must have minimum annual turnover of 5 Crores INR.",
            mandatory_status=MandatoryStatus.MANDATORY,
            rule_config={"type": "NUMERIC_MIN", "parameter": "turnover", "value": 50000000, "unit": "INR"},
            source_text="The bidder must have minimum annual turnover of 5 Crores INR.",
            page_number=2,
        )
        self.assertEqual(item.category, ClauseCategory.FINANCIAL)
        self.assertTrue(item.is_mandatory)
        self.assertEqual(item.rule_config["type"], "NUMERIC_MIN")
        self.assertEqual(item.page_number, 2)

    def test_category_normalization_aliases(self):
        # Commercial / Turnover -> FINANCIAL
        item1 = ExtractedClauseItem(
            category="COMMERCIAL",
            title="Annual Turnover",
            description="Turnover must be 1 Crore",
            source_text="Turnover must be 1 Crore",
            page_number=1,
        )
        self.assertEqual(item1.category, ClauseCategory.FINANCIAL)

        # Statutory / MSME -> STATUTORY
        item2 = ExtractedClauseItem(
            category="STATUTORY_MII",
            title="Make in India Content",
            description="Minimum 50 percent local content required",
            source_text="Minimum 50 percent local content required",
            page_number=1,
        )
        self.assertEqual(item2.category, ClauseCategory.STATUTORY)

        # SLA -> DELIVERY_SLA
        item3 = ExtractedClauseItem(
            category="SLA_PENALTY",
            title="Liquidated Damages",
            description="0.5% per week penalty",
            source_text="0.5% per week penalty",
            page_number=3,
        )
        self.assertEqual(item3.category, ClauseCategory.DELIVERY_SLA)

    def test_mandatory_status_and_is_mandatory_derivation(self):
        # Explicitly optional
        item_opt = ExtractedClauseItem(
            category="TECHNICAL",
            title="ISO 27001 Certification",
            description="ISO 27001 is desirable but not mandatory.",
            mandatory_status="OPTIONAL",
            source_text="ISO 27001 is desirable but not mandatory.",
            page_number=1,
        )
        self.assertFalse(item_opt.is_mandatory)
        self.assertEqual(item_opt.mandatory_status, MandatoryStatus.OPTIONAL)

        # Ambiguous / unclear -> treated as mandatory qualification flag + draft review
        item_unc = ExtractedClauseItem(
            category="TECHNICAL",
            title="OEM Authorization",
            description="OEM certificate may be submitted.",
            mandatory_status="UNCLEAR",
            source_text="OEM certificate may be submitted.",
            page_number=2,
            rule_config={"type": "CUSTOM", "parameter": "oem_auth"},
        )
        self.assertTrue(item_unc.is_mandatory)
        self.assertEqual(item_unc.mandatory_status, MandatoryStatus.UNCLEAR)
        self.assertTrue(item_unc.rule_config["requires_human_review"])

    def test_rule_type_bounds_and_fallback(self):
        item_valid_rule = ExtractedClauseItem(
            category="FINANCIAL",
            title="EMD Exemption",
            description="EMD is exempted for MSME",
            rule_config={"type": "BOOLEAN_CERT", "parameter": "msme_certificate", "value": True},
            source_text="EMD is exempted for MSME",
            page_number=1,
        )
        self.assertEqual(item_valid_rule.rule_config["type"], "BOOLEAN_CERT")

        item_unknown_rule = ExtractedClauseItem(
            category="TECHNICAL",
            title="Complex Spec",
            description="Special spec",
            rule_config={"type": "NON_EXISTENT_TYPE", "parameter": "spec"},
            source_text="Special spec text here",
            page_number=1,
        )
        self.assertEqual(item_unknown_rule.rule_config["type"], "CUSTOM")
        self.assertTrue(item_unknown_rule.rule_config["requires_human_review"])


class TestPdfExtractor(unittest.TestCase):
    def test_extract_pages_from_synthetic_pdf(self):
        doc = pymupdf.open()
        page1 = doc.new_page()
        page1.insert_text((50, 72), "Government e-Marketplace Tender\nRequirement 1: Bidder must have ISO 9001 certification.")
        page2 = doc.new_page()
        page2.insert_text((50, 72), "Financial Qualification\nMinimum annual turnover shall be 2 Crores INR.")
        page3 = doc.new_page()
        page3.insert_text((50, 72), "Delivery SLA\nDelivery must be completed within 30 days of contract award.")

        pdf_bytes = doc.write()
        doc.close()

        pages_data = extract_pages_from_pdf(pdf_bytes)
        self.assertEqual(len(pages_data), 3)
        self.assertEqual(pages_data[0]["page_number"], 1)
        self.assertEqual(pages_data[1]["page_number"], 2)
        self.assertEqual(pages_data[2]["page_number"], 3)
        self.assertIn("ISO 9001", pages_data[0]["text"])
        self.assertIn("2 Crores INR", pages_data[1]["text"])
        self.assertIn("30 days", pages_data[2]["text"])
        self.assertFalse(pages_data[0]["is_empty"])


class TestProvenanceAndCompletenessValidation(unittest.TestCase):
    def setUp(self):
        self.sample_window = [
            {
                "page_number": 1,
                "text": "The bidder must possess a valid ISO 9001:2015 quality management certification."
            },
            {
                "page_number": 2,
                "text": "Average annual turnover of the bidder during the last three financial years must be at least INR 50 Lakhs."
            },
            {
                "page_number": 4,
                "text": "Delay in supply will attract liquidated damages of 0.5 percent per week of delay subject to a maximum cap of 10 percent."
            }
        ]

    def test_valid_complete_quote_acceptance(self):
        # Full complete quote
        quote = "Delay in supply will attract liquidated damages of 0.5 percent per week of delay subject to a maximum cap of 10 percent."
        ok, page, reason = verify_source_text_presence(quote, self.sample_window)
        self.assertTrue(ok, f"Expected quote to be accepted, but rejected: {reason}")
        self.assertEqual(page, 4)
        self.assertEqual(reason, "")

        # Another complete clause on page 1
        quote1 = "The bidder must possess a valid ISO 9001:2015 quality management certification."
        ok1, page1, reason1 = verify_source_text_presence(quote1, self.sample_window)
        self.assertTrue(ok1)
        self.assertEqual(page1, 1)

    def test_truncated_source_text_rejection_mid_word(self):
        # Truncated mid-word quote ("10 pe" instead of "10 percent")
        truncated_mid_word = "Delay in supply will attract liquidated damages of 0.5 percent per week of delay subject to a maximum cap of 10 pe"
        ok, page, reason = verify_source_text_presence(truncated_mid_word, self.sample_window)
        self.assertFalse(ok, "Expected mid-word truncated quote to be rejected")
        self.assertEqual(page, 0)
        self.assertIn("mid-word", reason.lower())
        self.assertIn("pe", reason)

    def test_incomplete_quote_rejection_dropped_unit(self):
        # Dropped critical unit "percent" after "10"
        truncated_unit = "Delay in supply will attract liquidated damages of 0.5 percent per week of delay subject to a maximum cap of 10"
        ok, page, reason = verify_source_text_presence(truncated_unit, self.sample_window)
        self.assertFalse(ok, "Expected dropped unit quote to be rejected")
        self.assertEqual(page, 0)
        self.assertIn("dropped critical unit", reason.lower())

    def test_incomplete_quote_rejection_dangling_ending(self):
        # Ends with dangling preposition "of"
        dangling_quote = "Delay in supply will attract liquidated damages of 0.5 percent per week of delay subject to a maximum cap of"
        ok, page, reason = verify_source_text_presence(dangling_quote, self.sample_window)
        self.assertFalse(ok, "Expected dangling ending quote to be rejected")
        self.assertEqual(page, 0)
        self.assertIn("dangling", reason.lower())

        # Ends with ellipsis
        ellipsis_quote = "Delay in supply will attract liquidated damages of 0.5 percent per week..."
        ok_el, _, reason_el = verify_source_text_presence(ellipsis_quote, self.sample_window)
        self.assertFalse(ok_el)
        self.assertIn("ellipsis", reason_el.lower())

    def test_fabricated_quote_rejection(self):
        fabricated = "Bidder must have completed 5 similar railway projects worth 100 Crores."
        ok, page, reason = verify_source_text_presence(fabricated, self.sample_window)
        self.assertFalse(ok)
        self.assertEqual(page, 0)


class TestClauseDeduplicationAndCoding(unittest.TestCase):
    def test_deduplicate_clauses_preserves_richest_quote(self):
        clauses = [
            ExtractedRawClause(
                category="FINANCIAL",
                title="Minimum Annual Turnover",
                description="Turnover of 5 Crores",
                is_mandatory=True,
                mandatory_status="MANDATORY",
                rule_config={"type": "NUMERIC_MIN", "parameter": "turnover", "value": 50000000},
                source_text="Turnover must be 5 Crores.",
                page_number=3,
            ),
            ExtractedRawClause(
                category="FINANCIAL",
                title="Minimum Annual Turnover",
                description="Turnover of 5 Crores INR in last 3 financial years",
                is_mandatory=True,
                mandatory_status="MANDATORY",
                rule_config={"type": "NUMERIC_MIN", "parameter": "turnover", "value": 50000000, "unit": "INR"},
                source_text="Average annual turnover of the bidder during the last three financial years must be at least 5 Crores INR.",
                page_number=4,
            ),
        ]

        deduped = deduplicate_clauses(clauses)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].page_number, 3)
        self.assertIn("Average annual turnover", deduped[0].source_text)

    def test_assign_clause_codes_sequential_per_category(self):
        clauses = [
            ExtractedRawClause(
                category="TECHNICAL",
                title="ISO Certification",
                description="ISO 9001 required",
                source_text="ISO 9001 required",
                page_number=1,
            ),
            ExtractedRawClause(
                category="TECHNICAL",
                title="Warranty Period",
                description="3 years warranty",
                source_text="3 years warranty",
                page_number=2,
            ),
            ExtractedRawClause(
                category="FINANCIAL",
                title="Turnover",
                description="Turnover 1 Cr",
                source_text="Turnover 1 Cr",
                page_number=2,
            ),
            ExtractedRawClause(
                category="STATUTORY",
                title="Make in India",
                description="50% MII",
                source_text="50% MII",
                page_number=3,
            ),
        ]
        seq_tracker = {"TECH": 1, "FIN": 1, "STAT": 1, "EXP": 1, "DEL": 1}
        assigned, updated_seq = assign_clause_codes(clauses, seq_tracker)

        self.assertEqual(assigned[0]["clause_code"], "TECH-01")
        self.assertEqual(assigned[1]["clause_code"], "TECH-02")
        self.assertEqual(assigned[2]["clause_code"], "FIN-01")
        self.assertEqual(assigned[3]["clause_code"], "STAT-01")
        self.assertEqual(updated_seq["TECH"], 3)
        self.assertEqual(updated_seq["FIN"], 2)
        self.assertEqual(updated_seq["STAT"], 2)


class TestTimeoutFallbackAndDegradation(unittest.TestCase):
    def test_window_degradation_3page_to_2page(self):
        """When a 3-page window times out/fails twice, it must gracefully degrade to 2-page sub-windows."""
        window_3page = [
            {"page_number": 1, "text": "Hardware: Rack servers must be equipped with 64-core processors."},
            {"page_number": 2, "text": "Turnover: Average annual turnover must be at least INR 5.0 Crores."},
            {"page_number": 3, "text": "Local Content: Minimum 50 percent local content is mandatory."}
        ]

        audit_report = {
            "successful_windows": [],
            "fallback_windows": [],
            "rejected_clauses": [],
            "failed_pages": []
        }

        # Mock LLM calls: fail on 3-page window [1, 2, 3], but succeed on 2-page sub-windows [1, 2] and [2, 3]
        async def mock_llm_call(win, timeout_sec=50.0):
            p_nums = [p["page_number"] for p in win]
            if len(win) == 3:
                raise TimeoutError("Simulated NVIDIA NIM 3-page timeout")
            elif p_nums == [1, 2]:
                return {
                    "clauses": [
                        {
                            "category": "TECHNICAL",
                            "title": "Rack Server Processors",
                            "description": "64-core processors required",
                            "mandatory_status": "MANDATORY",
                            "rule_config": {"type": "NUMERIC_MIN", "parameter": "cores", "value": 64},
                            "source_text": "Hardware: Rack servers must be equipped with 64-core processors.",
                            "page_number": 1
                        }
                    ]
                }
            elif p_nums == [2, 3]:
                return {
                    "clauses": [
                        {
                            "category": "STATUTORY",
                            "title": "Local Content Requirement",
                            "description": "50% local content required",
                            "mandatory_status": "MANDATORY",
                            "rule_config": {"type": "PERCENT_MIN", "parameter": "local_content", "value": 50},
                            "source_text": "Local Content: Minimum 50 percent local content is mandatory.",
                            "page_number": 3
                        }
                    ]
                }
            return {"clauses": []}

        with patch("app.services.clause_extractor._call_llm_for_window", side_effect=mock_llm_call):
            clauses = asyncio.run(process_window_with_degradation(window_3page, audit_report))

        # Must have extracted clauses from the degraded 2-page windows
        self.assertEqual(len(clauses), 2)
        titles = [c.title for c in clauses]
        self.assertIn("Rack Server Processors", titles)
        self.assertIn("Local Content Requirement", titles)

        # Must have recorded the fallback event
        self.assertEqual(len(audit_report["fallback_windows"]), 1)
        fallback = audit_report["fallback_windows"][0]
        self.assertEqual(fallback["original_pages"], [1, 2, 3])
        self.assertIn("2-page sub-windows", fallback["degraded_to"])

    def test_window_degradation_full_hierarchy_to_1page(self):
        """When 3-page and 2-page windows fail, it must degrade to 1-page windows."""
        window_3page = [
            {"page_number": 1, "text": "Hardware: Rack servers must be equipped with 64-core processors."},
            {"page_number": 2, "text": "Turnover: Average annual turnover must be at least INR 5.0 Crores."},
            {"page_number": 3, "text": "Local Content: Minimum 50 percent local content is mandatory."}
        ]

        audit_report = {
            "successful_windows": [],
            "fallback_windows": [],
            "rejected_clauses": [],
            "failed_pages": []
        }

        # Mock LLM calls: fail on len 3 and len 2, succeed on single page
        async def mock_llm_call(win, timeout_sec=50.0):
            p_nums = [p["page_number"] for p in win]
            if len(win) >= 2:
                raise TimeoutError(f"Simulated timeout on pages {p_nums}")
            elif p_nums == [1]:
                return {
                    "clauses": [
                        {
                            "category": "TECHNICAL",
                            "title": "Rack Server Processors",
                            "description": "64-core processors required",
                            "mandatory_status": "MANDATORY",
                            "rule_config": {"type": "NUMERIC_MIN", "parameter": "cores", "value": 64},
                            "source_text": "Hardware: Rack servers must be equipped with 64-core processors.",
                            "page_number": 1
                        }
                    ]
                }
            return {"clauses": []}

        with patch("app.services.clause_extractor._call_llm_for_window", side_effect=mock_llm_call):
            clauses = asyncio.run(process_window_with_degradation(window_3page, audit_report))

        # Successfully recovered page 1 clause
        self.assertEqual(len(clauses), 1)
        self.assertEqual(clauses[0].title, "Rack Server Processors")

        # Must record fallback chain
        self.assertGreaterEqual(len(audit_report["fallback_windows"]), 2)
        degraded_destinations = [f["degraded_to"] for f in audit_report["fallback_windows"]]
        self.assertTrue(any("2-page" in d for d in degraded_destinations))
        self.assertTrue(any("1-page" in d for d in degraded_destinations))


if __name__ == "__main__":
    unittest.main()
