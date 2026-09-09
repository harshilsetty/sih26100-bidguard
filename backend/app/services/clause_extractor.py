import logging
import re
import json
import asyncio
from typing import List, Dict, Any, Tuple, Optional, Union
from pydantic import ValidationError

from app.services.nvidia_client import get_nvidia_client
from app.schemas.clause import (
    ExtractedRawClause,
    ExtractedClauseItem,
    LLMExtractionBatch,
    ClauseCategory,
    MandatoryStatus,
    RuleType,
    DraftRuleConfig,
)

logger = logging.getLogger(__name__)

CATEGORY_PREFIX_MAP = {
    "TECHNICAL": "TECH",
    "FINANCIAL": "FIN",
    "STATUTORY": "STAT",
    "EXPERIENCE": "EXP",
    "DELIVERY_SLA": "DEL",
}

# Words that indicate an incomplete, mid-sentence, or dangling quote
DANGLING_ENDINGS = {
    "and", "or", "of", "to", "the", "in", "with", "for", "a", "an", "by", "at",
    "as", "from", "that", "which", "is", "are", "be", "subject", "per", "minimum",
    "maximum", "cap", "than", "more", "less", "such", "not", "no", "pe"
}

# Essential units/quantifiers that must not be stripped if immediately following a digit
CRITICAL_UNITS = {
    "percent", "%", "lakhs", "crores", "lakh", "crore", "days", "months", "years",
    "inr", "rs", "rupees", "hours", "weeks", "gb", "mb", "cores", "core", "tb"
}

EXTRACTION_SYSTEM_PROMPT = """You are an expert Government e-Marketplace (GeM) tender compliance auditor.
Your job is to read tender document excerpts and extract all binding, verifiable compliance requirements and specifications into a structured JSON array.

Categories allowed:
- "TECHNICAL": Hardware/software specs, capacity, standards, certifications (e.g. ISO, BIS), warranty, performance criteria.
- "FINANCIAL": Minimum annual turnover, net worth, solvency, EMD (Earnest Money Deposit), PBG (Performance Bank Guarantee).
- "STATUTORY": Make-in-India (MII local content %), MSME exemptions, GST, PAN, non-blacklisting / non-debarment declarations.
- "EXPERIENCE": Past performance criteria, similar contract execution count & value, years of experience.
- "DELIVERY_SLA": Delivery timelines, milestones, SLA penalties, liquidated damages.

Strict Provenance & Completeness Rules:
1. "source_text" MUST be a COMPLETE verbatim sentence or clause directly from the provided text.
   - DO NOT truncate words mid-token (e.g. DO NOT write "10 pe" instead of "10 percent").
   - DO NOT cut off sentences mid-phrase or omit trailing units/percentages.
   - Incomplete or truncated quotes WILL BE STRICTLY REJECTED by automated provenance verification.
2. "page_number" MUST be the exact integer page number where that verbatim sentence appears, matching the "=== PAGE X START ===" markers.
3. "mandatory_status": Classify explicitly as:
   - "MANDATORY": Language indicates an obligatory requirement (e.g. "must", "shall", "required", "mandatory", "minimum", "will result in rejection").
   - "OPTIONAL": Language indicates a preference or desirable condition (e.g. "preferable", "desirable", "optional", "may").
   - "UNCLEAR": Language is ambiguous, poorly phrased, or lacks explicit rejection criteria. These will be flagged for human officer review.
4. "rule_config": If quantifiable or verifiable, output a draft rule config object with "type" chosen from:
   ["NUMERIC_MIN", "NUMERIC_MAX", "BOOLEAN_CERT", "PERCENT_MIN", "DOCUMENT_REQUIRED", "CUSTOM"].
   Include fields "parameter", "value", and "unit" where applicable. If uncertain, use null or type "CUSTOM".

CRITICAL OUTPUT FORMAT:
You MUST output ONLY a valid JSON object matching the schema below.
DO NOT include any commentary, explanations, reasoning thoughts, or conversational preambles before or after the JSON.
Start your response immediately with "{" and end with "}".

{
  "clauses": [
    {
      "category": "TECHNICAL",
      "title": "Short title",
      "description": "Complete requirement text specifying conditions, values, and criteria",
      "mandatory_status": "MANDATORY",
      "rule_config": {
        "type": "NUMERIC_MIN",
        "parameter": "annual_turnover",
        "value": 5000000,
        "unit": "INR"
      },
      "source_text": "Exact complete verbatim quote from tender text...",
      "page_number": 1
    }
  ]
}

If no compliance requirements appear in the excerpt, return: {"clauses": []}
"""


def build_page_windows(
    pages_data: List[Dict[str, Any]],
    window_size: int = 3,
    stride: int = 2
) -> List[List[Dict[str, Any]]]:
    """Create 3-page sliding windows with 1-page overlap (stride=2)."""
    total = len(pages_data)
    if total == 0:
        return []
    if total <= window_size:
        return [pages_data]

    windows: List[List[Dict[str, Any]]] = []
    start = 0
    while start < total:
        end = min(start + window_size, total)
        windows.append(pages_data[start:end])
        if end == total:
            break
        start += stride

    return windows


def format_window_text(window: List[Dict[str, Any]]) -> str:
    """Format a group of pages with clear provenance markers for the LLM."""
    chunks = []
    for page in window:
        p_num = page["page_number"]
        p_text = page["text"]
        chunks.append(f"=== PAGE {p_num} START ===\n{p_text}\n=== PAGE {p_num} END ===")
    return "\n\n".join(chunks)


def _tokenize_text(text: str) -> List[str]:
    """Extract normalized alphanumeric word tokens."""
    return [w.lower() for w in re.findall(r"\b[a-zA-Z0-9_%.-]+\b", text)]


def verify_source_text_presence(
    source_text: str,
    window: List[Dict[str, Any]]
) -> Tuple[bool, int, str]:
    """Conservative provenance validation hierarchy ensuring source_text is a COMPLETE, verifiable quote.
    Rejects:
    - Truncated quotes or mid-token cuts (e.g. '10 pe' instead of '10 percent').
    - Quotes ending with ellipsis ('...' or '…').
    - Quotes ending with dangling prepositions or connectors (e.g. 'cap of', 'subject to').
    - Quotes dropping critical units immediately following a numeric value.
    - Fabricated or ungrounded quotes.

    Returns:
        (is_verified: bool, exact_page_number: int, rejection_reason: str)
    """
    raw_source = source_text.strip()
    if not raw_source:
        return False, 0, "Source text is empty"

    # Check 1: Ellipsis / explicit truncation markers
    if raw_source.endswith(("...", "…")):
        return False, 0, "Source quote ends with ellipsis indicating truncated quote"

    source_tokens = _tokenize_text(raw_source)
    if len(source_tokens) < 3:
        return False, 0, f"Source quote is too brief ({len(source_tokens)} tokens) to establish verifiable provenance"

    last_token = source_tokens[-1]

    # Check 2: Dangling prepositions or incomplete clause endings
    if last_token in DANGLING_ENDINGS:
        return False, 0, f"Source quote ends with dangling/incomplete token or mid-word cut '{last_token}'"

    k = len(source_tokens)

    # Search window pages for exact token sequence
    for page in window:
        page_tokens = _tokenize_text(page["text"])
        p_len = len(page_tokens)
        if p_len < k:
            continue

        # Check for exact contiguous token match
        for i in range(p_len - k + 1):
            if page_tokens[i : i + k] == source_tokens:
                # Token sequence matched!
                # Check 3: Ensure critical unit was not dropped after numeric token
                if i + k < p_len:
                    next_page_token = page_tokens[i + k]
                    clean_last = last_token.replace(".", "")
                    if clean_last.isdigit() and next_page_token in CRITICAL_UNITS:
                        return False, 0, (
                            f"Source quote dropped critical unit '{next_page_token}' "
                            f"immediately following '{last_token}'"
                        )

                # Verified exact complete quote on this page!
                return True, page["page_number"], ""

        # Check for mid-token cut: e.g. prefix matches but last token was truncated
        # If source_tokens[:-1] matches page_tokens[i : i + k - 1] and page_tokens[i + k - 1].startswith(last_token)
        for i in range(p_len - k + 1):
            if page_tokens[i : i + k - 1] == source_tokens[:-1]:
                expected_full_token = page_tokens[i + k - 1]
                if expected_full_token != last_token and expected_full_token.startswith(last_token):
                    return False, 0, (
                        f"Source quote ends mid-word: '{last_token}' is a truncated prefix of '{expected_full_token}'"
                    )

    # If no exact contiguous sequence, reject to prevent fabrication
    return False, 0, "Source text quote could not be confirmed as a complete verbatim sequence in the excerpt"


def normalize_title(title: str) -> str:
    """Normalize requirement title for duplicate checking."""
    return re.sub(r"[^a-zA-Z0-9]", "", title.lower())


def deduplicate_clauses(clauses: List[ExtractedRawClause]) -> List[ExtractedRawClause]:
    """Deduplicate clauses extracted across overlapping windows.
    Preserves earliest page occurrence, richest source text, and conservative mandatory status.
    """
    unique_clauses: List[ExtractedRawClause] = []

    for candidate in clauses:
        cand_norm = normalize_title(candidate.title)
        cand_title_words = set(candidate.title.lower().split())
        cand_source_words = set(_tokenize_text(candidate.source_text))

        duplicate_index = -1

        for idx, existing in enumerate(unique_clauses):
            if existing.category != candidate.category:
                continue

            exist_norm = normalize_title(existing.title)
            exist_title_words = set(existing.title.lower().split())
            exist_source_words = set(_tokenize_text(existing.source_text))

            # 1. Exact normalized title match
            if cand_norm and cand_norm == exist_norm:
                duplicate_index = idx
                break

            # 2. High title token overlap (Jaccard >= 0.75)
            if cand_title_words and exist_title_words:
                jaccard_title = len(cand_title_words & exist_title_words) / len(cand_title_words | exist_title_words)
                if jaccard_title >= 0.75:
                    duplicate_index = idx
                    break

            # 3. High source text quote overlap (>= 75% containment)
            if cand_source_words and exist_source_words:
                min_len = min(len(cand_source_words), len(exist_source_words))
                if min_len > 0:
                    containment = len(cand_source_words & exist_source_words) / min_len
                    if containment >= 0.75:
                        duplicate_index = idx
                        break

        if duplicate_index == -1:
            unique_clauses.append(candidate)
        else:
            # Merge duplicate: preserve richest source text and conservative mandatory status
            existing = unique_clauses[duplicate_index]
            earliest_page = min(existing.page_number, candidate.page_number)

            richer_source = candidate.source_text if len(candidate.source_text) > len(existing.source_text) else existing.source_text
            richer_desc = candidate.description if len(candidate.description) > len(existing.description) else existing.description

            is_mand = existing.is_mandatory or candidate.is_mandatory
            if existing.mandatory_status == "MANDATORY" or candidate.mandatory_status == "MANDATORY":
                mand_status = "MANDATORY"
            elif existing.mandatory_status == "UNCLEAR" or candidate.mandatory_status == "UNCLEAR":
                mand_status = "UNCLEAR"
            else:
                mand_status = "OPTIONAL"

            rule_config = candidate.rule_config or existing.rule_config

            unique_clauses[duplicate_index] = ExtractedRawClause(
                category=candidate.category,
                title=candidate.title,
                description=richer_desc,
                is_mandatory=is_mand,
                mandatory_status=mand_status,
                rule_config=rule_config,
                source_text=richer_source,
                page_number=earliest_page,
            )

    return unique_clauses


def assign_clause_codes(
    clauses: List[ExtractedRawClause],
    seq_tracker: Dict[str, int]
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Assign stable, category-based sequential codes (TECH-01, FIN-01, STAT-01, EXP-01, DEL-01)."""
    assigned = []
    tracker = dict(seq_tracker)

    for raw in clauses:
        prefix = CATEGORY_PREFIX_MAP.get(raw.category.upper(), "GEN")
        current_seq = tracker.get(prefix, 1)
        code = f"{prefix}-{current_seq:02d}"
        tracker[prefix] = current_seq + 1

        assigned.append({
            "clause_code": code,
            "category": raw.category.upper(),
            "title": raw.title.strip(),
            "description": raw.description.strip(),
            "is_mandatory": raw.is_mandatory,
            "mandatory_status": raw.mandatory_status,
            "rule_config": raw.rule_config,
            "source_text": raw.source_text.strip(),
            "page_number": raw.page_number,
            "is_confirmed": False,
        })

    return assigned, tracker


async def _call_llm_for_window(
    window: List[Dict[str, Any]],
    timeout_sec: float = 50.0
) -> Dict[str, Any]:
    """Direct call to NVIDIA NIM LLM for a specific window with bounded timeout."""
    nvidia = get_nvidia_client()
    pages_in_win = [p["page_number"] for p in window]
    formatted_text = format_window_text(window)
    user_prompt = f"Analyze the following tender excerpt (Pages {pages_in_win[0]} to {pages_in_win[-1]}):\n\n{formatted_text}"

    res_json = await nvidia.structured_completion(
        prompt=user_prompt,
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        temperature=0.0,
        max_tokens=1536,
        timeout=timeout_sec,
    )
    return res_json


async def process_window_with_degradation(
    window: List[Dict[str, Any]],
    audit_report: Dict[str, Any]
) -> List[ExtractedRawClause]:
    """Graceful window processing with 3-page -> retry -> 2-page -> 1-page degradation.
    Ensures no failed window is silently lost.
    """
    pages_in_win = [p["page_number"] for p in window]
    win_len = len(window)

    # Adaptive timeout based on window size (75s bounded timeout to prevent unnecessary fallback)
    timeout_sec = 75.0

    # Attempt 1
    logger.info(f"Extracting clauses from window {pages_in_win} (Attempt 1, timeout={timeout_sec}s)...")
    res_json = None
    last_error = None

    try:
        res_json = await _call_llm_for_window(window, timeout_sec=timeout_sec)
    except Exception as e:
        last_error = str(e)
        logger.warning(f"Attempt 1 failed for window {pages_in_win}: {e}")

    # Retry once if Attempt 1 failed or returned empty/malformed
    if not res_json or "clauses" not in res_json or ("raw_response" in res_json and not res_json.get("clauses")):
        logger.info(f"Retrying window {pages_in_win} (Attempt 2)...")
        try:
            res_json = await _call_llm_for_window(window, timeout_sec=timeout_sec)
            last_error = None
        except Exception as retry_err:
            last_error = str(retry_err)
            logger.warning(f"Attempt 2 (retry) failed for window {pages_in_win}: {retry_err}")

    # If successful, parse clauses
    if res_json and ("clauses" in res_json or isinstance(res_json, list)):
        raw_list = res_json if isinstance(res_json, list) else res_json.get("clauses", [])
        if raw_list:
            parsed_clauses: List[ExtractedRawClause] = []
            try:
                batch = LLMExtractionBatch.model_validate({"clauses": raw_list})
                for item in batch.clauses:
                    # Strict complete quote provenance verification
                    verified, matched_page, reason = verify_source_text_presence(item.source_text, window)
                    if not verified:
                        logger.warning(f"Rejecting clause '{item.title}': {reason}")
                        audit_report["rejected_clauses"].append({
                            "title": item.title,
                            "reason": reason,
                            "source_text": item.source_text,
                            "page_number": item.page_number
                        })
                        continue

                    actual_page = matched_page if matched_page > 0 else item.page_number
                    parsed_clauses.append(ExtractedRawClause(
                        category=item.category.value,
                        title=item.title,
                        description=item.description,
                        is_mandatory=item.is_mandatory,
                        mandatory_status=item.mandatory_status.value,
                        rule_config=item.rule_config,
                        source_text=item.source_text,
                        page_number=actual_page,
                    ))

                audit_report["successful_windows"].append(pages_in_win)
                return parsed_clauses

            except ValidationError as val_err:
                logger.error(f"Pydantic validation error in window {pages_in_win}: {val_err}")
                last_error = f"Schema validation failed: {val_err}"

    # If extraction still failed, trigger degradation fallback!
    logger.warning(
        f"Window {pages_in_win} failed after retry ({last_error}). Triggering window degradation fallback."
    )

    if win_len == 3:
        # Degrade 3-page window to two 2-page sub-windows with 1-page overlap
        sub_windows = [
            [window[0], window[1]],
            [window[1], window[2]],
        ]
        sub_desc = [[p["page_number"] for p in sw] for sw in sub_windows]
        audit_report["fallback_windows"].append({
            "original_pages": pages_in_win,
            "reason": last_error or "Extraction failed",
            "degraded_to": f"2-page sub-windows: {sub_desc}"
        })
        logger.info(f"Degraded 3-page window {pages_in_win} to 2-page sub-windows: {sub_desc}")

        degraded_clauses: List[ExtractedRawClause] = []
        for sw in sub_windows:
            sub_results = await process_window_with_degradation(sw, audit_report)
            degraded_clauses.extend(sub_results)

        return deduplicate_clauses(degraded_clauses)

    elif win_len == 2:
        # Degrade 2-page window to two 1-page sub-windows
        sub_windows = [
            [window[0]],
            [window[1]],
        ]
        sub_desc = [[p["page_number"] for p in sw] for sw in sub_windows]
        audit_report["fallback_windows"].append({
            "original_pages": pages_in_win,
            "reason": last_error or "Extraction failed",
            "degraded_to": f"1-page sub-windows: {sub_desc}"
        })
        logger.info(f"Degraded 2-page window {pages_in_win} to 1-page sub-windows: {sub_desc}")

        degraded_clauses: List[ExtractedRawClause] = []
        for sw in sub_windows:
            sub_results = await process_window_with_degradation(sw, audit_report)
            degraded_clauses.extend(sub_results)

        return deduplicate_clauses(degraded_clauses)

    else:
        # Single page failed after retry
        logger.error(f"Single page window {pages_in_win} failed permanently: {last_error}")
        audit_report["failed_pages"].append({
            "page_number": pages_in_win[0],
            "error": last_error or "Unknown failure"
        })
        return []


async def extract_clauses_from_tender_pages(
    pages_data: List[Dict[str, Any]],
    current_seq_tracker: Dict[str, int],
    return_report: bool = False
) -> Union[Tuple[List[Dict[str, Any]], Dict[str, int]], Tuple[List[Dict[str, Any]], Dict[str, int], Dict[str, Any]]]:
    """Execute source-grounded clause extraction across 3-page sliding windows with
    graceful timeout degradation (3-page -> retry -> 2-page -> 1-page) and strict completeness provenance verification.
    """
    windows = build_page_windows(pages_data, window_size=3, stride=2)
    logger.info(f"Processing tender across {len(windows)} initial page windows (3-page windows with 1-page overlap).")

    audit_report: Dict[str, Any] = {
        "original_window_count": len(windows),
        "successful_windows": [],
        "fallback_windows": [],
        "rejected_clauses": [],
        "failed_pages": [],
        "final_clause_count": 0,
    }

    all_extracted_clauses: List[ExtractedRawClause] = []

    for window in windows:
        win_clauses = await process_window_with_degradation(window, audit_report)
        all_extracted_clauses.extend(win_clauses)

    logger.info(f"Total raw clauses gathered across windows and fallbacks: {len(all_extracted_clauses)}")

    # Deduplicate across windows and degraded sub-windows
    unique_clauses = deduplicate_clauses(all_extracted_clauses)
    logger.info(f"Unique clauses after deduplication: {len(unique_clauses)}")

    # Assign category-based sequential codes (TECH-01, FIN-01, etc.)
    final_clauses, updated_seq_tracker = assign_clause_codes(unique_clauses, current_seq_tracker)
    audit_report["final_clause_count"] = len(final_clauses)

    if return_report:
        return final_clauses, updated_seq_tracker, audit_report
    return final_clauses, updated_seq_tracker
