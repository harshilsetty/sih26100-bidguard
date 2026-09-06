import logging
import re
import json
from typing import List, Dict, Any, Tuple
from app.services.nvidia_client import get_nvidia_client
from app.schemas.clause import ExtractedRawClause

logger = logging.getLogger(__name__)

CATEGORY_PREFIX_MAP = {
    "TECHNICAL": "TECH",
    "FINANCIAL": "FIN",
    "STATUTORY": "STAT",
    "EXPERIENCE": "EXP",
    "DELIVERY_SLA": "DEL",
}

EXTRACTION_SYSTEM_PROMPT = """You are an expert Government e-Marketplace (GeM) tender compliance auditor.
Your job is to read tender document excerpts and extract all binding, verifiable compliance requirements and specifications into a structured JSON array.

Categories allowed:
- "TECHNICAL": Hardware/software specs, capacity, standards, certifications (e.g. ISO), warranty, performance criteria.
- "FINANCIAL": Minimum annual turnover, net worth, solvency, EMD (Earnest Money Deposit), PBG (Performance Bank Guarantee).
- "STATUTORY": Make-in-India (MII local content %), MSME exemptions, GST, PAN, blacklisting declarations.
- "EXPERIENCE": Past performance criteria, similar contract execution count & value.
- "DELIVERY_SLA": Delivery timelines, milestones, SLA penalties, liquidated damages.

For each requirement, you MUST produce:
- "category": One of ["TECHNICAL", "FINANCIAL", "STATUTORY", "EXPERIENCE", "DELIVERY_SLA"]
- "title": Short concise title of the requirement (e.g., "Minimum Average Annual Turnover")
- "description": Complete requirement text specifying conditions, values, and criteria
- "is_mandatory": boolean (true if failure causes bid rejection, false if optional/desirable)
- "rule_config": draft machine-evaluable rule, e.g. {"type": "NUMERIC_MIN", "value": 5000000, "unit": "INR"} or {"type": "BOOLEAN_CERT", "cert": "ISO 9001"} or {"type": "PERCENT_MIN", "value": 50}
- "source_text": verbatim sentence or phrase from the provided text that proves this requirement. DO NOT invent or paraphrase text.
- "page_number": integer page number where the requirement appears

Return STRICT JSON format:
{
  "clauses": [
    ...
  ]
}
If no compliance requirements appear in the excerpt, return: {"clauses": []}
"""


def build_page_windows(pages_data: List[Dict[str, Any]], window_size: int = 3, stride: int = 2) -> List[List[Dict[str, Any]]]:
    """Create 3-page sliding windows with 1-page overlap (stride=2).
    
    Example for 6 pages:
    - Window 0: pages 1, 2, 3
    - Window 1: pages 3, 4, 5
    - Window 2: pages 5, 6
    """
    total = len(pages_data)
    if total <= window_size:
        return [pages_data] if pages_data else []

    windows = []
    start = 0
    while start < total:
        end = min(start + window_size, total)
        window = pages_data[start:end]
        windows.append(window)
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


def verify_source_text_presence(source_text: str, window: List[Dict[str, Any]]) -> Tuple[bool, int]:
    """Verify that source_text is actually grounded in the provided window pages.
    Returns (is_verified, actual_page_number).
    """
    cleaned_source = re.sub(r"\s+", " ", source_text.strip().lower())
    if len(cleaned_source) < 10:
        return False, 0

    # First check exact substring
    for page in window:
        page_clean = re.sub(r"\s+", " ", page["text"].lower())
        if cleaned_source in page_clean:
            return True, page["page_number"]

    # Fuzzy check: at least 70% word overlap with some sentence on the page
    source_words = set(cleaned_source.split())
    if not source_words:
        return False, 0

    best_match_page = 0
    best_overlap = 0.0

    for page in window:
        page_clean = re.sub(r"\s+", " ", page["text"].lower())
        page_words = set(page_clean.split())
        overlap = len(source_words.intersection(page_words)) / len(source_words)
        if overlap > best_overlap:
            best_overlap = overlap
            best_match_page = page["page_number"]

    if best_overlap >= 0.70:
        return True, best_match_page

    return False, 0


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", title.lower())


def deduplicate_clauses(clauses: List[ExtractedRawClause]) -> List[ExtractedRawClause]:
    """Deduplicate overlapping clauses while preserving provenance and richest source quote."""
    unique_clauses: List[ExtractedRawClause] = []

    for candidate in clauses:
        cand_norm = normalize_title(candidate.title)
        cand_words = set(candidate.title.lower().split())

        duplicate_index = -1
        for idx, existing in enumerate(unique_clauses):
            # Same category check
            if existing.category != candidate.category:
                continue

            exist_norm = normalize_title(existing.title)
            exist_words = set(existing.title.lower().split())

            # Exact normalized title match
            if cand_norm == exist_norm and cand_norm != "":
                duplicate_index = idx
                break

            # Word Jaccard similarity >= 0.75
            if cand_words and exist_words:
                jaccard = len(cand_words.intersection(exist_words)) / len(cand_words.union(exist_words))
                if jaccard >= 0.75:
                    duplicate_index = idx
                    break

        if duplicate_index == -1:
            unique_clauses.append(candidate)
        else:
            # Keep the one with longer source_text (richer evidence quote)
            existing = unique_clauses[duplicate_index]
            if len(candidate.source_text) > len(existing.source_text):
                unique_clauses[duplicate_index] = candidate

    return unique_clauses


def assign_clause_codes(
    clauses: List[ExtractedRawClause],
    seq_tracker: Dict[str, int]
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Assign stable, category-based sequential codes (e.g. TECH-01, FIN-01) without recycling."""
    assigned = []
    tracker = dict(seq_tracker)  # Copy

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
            "rule_config": raw.rule_config,
            "source_text": raw.source_text.strip(),
            "page_number": raw.page_number,
            "is_confirmed": False,
        })

    return assigned, tracker


async def extract_clauses_from_tender_pages(
    pages_data: List[Dict[str, Any]],
    current_seq_tracker: Dict[str, int]
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Process tender pages in 3-page windows with 1-page overlap, call NIM GPT-OSS 20B,
    validate evidence ground truth, deduplicate, and assign unique category codes.
    """
    nvidia = get_nvidia_client()
    windows = build_page_windows(pages_data, window_size=3, stride=2)
    logger.info(f"Processing tender across {len(windows)} page windows (3-page windows with 1-page overlap).")

    raw_extracted_clauses: List[ExtractedRawClause] = []

    for win_idx, window in enumerate(windows):
        pages_in_win = [p["page_number"] for p in window]
        logger.info(f"Extracting clauses from window {win_idx + 1}/{len(windows)} (Pages: {pages_in_win})...")

        formatted_text = format_window_text(window)
        user_prompt = f"Analyze the following tender excerpt (Pages {pages_in_win[0]} to {pages_in_win[-1]}):\n\n{formatted_text}"

        try:
            res_json = await nvidia.structured_completion(
                prompt=user_prompt,
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                temperature=1.0,
                max_tokens=2048
            )

            clauses_data = res_json.get("clauses", [])
            if isinstance(clauses_data, list):
                for item in clauses_data:
                    try:
                        # Extract basic fields
                        category = str(item.get("category", "TECHNICAL")).upper()
                        if category not in CATEGORY_PREFIX_MAP:
                            category = "TECHNICAL"

                        title = str(item.get("title", "")).strip()
                        description = str(item.get("description", "")).strip()
                        source_text = str(item.get("source_text", "")).strip()
                        page_number = int(item.get("page_number", pages_in_win[0]))
                        is_mandatory = bool(item.get("is_mandatory", True))
                        rule_config = item.get("rule_config") if isinstance(item.get("rule_config"), dict) else None

                        if not title or not description:
                            continue

                        # Grounding verification: ensure source_text is actually in this window!
                        verified, matched_page = verify_source_text_presence(source_text, window)
                        if verified:
                            if matched_page > 0:
                                page_number = matched_page
                        else:
                            # If the LLM didn't copy verbatim, find the sentence in the window closest to title
                            # or discard to prevent hallucinations
                            logger.warning(f"Unverified evidence snippet for clause '{title}'. Skipping to prevent hallucination.")
                            continue

                        raw_extracted_clauses.append(ExtractedRawClause(
                            category=category,
                            title=title,
                            description=description,
                            is_mandatory=is_mandatory,
                            rule_config=rule_config,
                            source_text=source_text,
                            page_number=page_number,
                        ))
                    except Exception as parse_err:
                        logger.warning(f"Failed to parse clause item: {parse_err}")
                        continue
        except Exception as win_err:
            logger.error(f"Error extracting clauses for window {pages_in_win}: {win_err}")
            continue

    # Deduplicate clauses across overlapping windows
    logger.info(f"Total raw clauses extracted across windows: {len(raw_extracted_clauses)}")
    unique_clauses = deduplicate_clauses(raw_extracted_clauses)
    logger.info(f"Unique clauses after deduplication: {len(unique_clauses)}")

    # Assign category-based sequential codes (TECH-01, FIN-01, etc.)
    final_clauses, updated_seq_tracker = assign_clause_codes(unique_clauses, current_seq_tracker)
    return final_clauses, updated_seq_tracker
