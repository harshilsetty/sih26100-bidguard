import re
import json
import logging
from typing import List, Dict, Any, Optional, Union
from app.schemas.bidder import RetrievedEvidenceChunk
from app.schemas.evaluation import AIEvidenceInterpretation, ParameterClaim
from app.services.nvidia_client import get_nvidia_client

logger = logging.getLogger(__name__)

INTERPRETATION_SYSTEM_PROMPT = """You are an AI Procurement Compliance Auditor for the Government of India GeM platform.
Your task is to analyze retrieved evidence chunks submitted by a bidder and extract factual claims regarding a specific tender compliance clause.

Rules:
1. Extract the exact value claimed or demonstrated by the bidder specifically for the target parameter of this clause.
2. Contradiction Detection: Only flag contradiction if there are conflicting or mutually exclusive values for the EXACT SAME target parameter. Do NOT flag a contradiction if an unrelated parameter has discrepancies.
3. Identify ambiguous, expired, or pending compliance for the target parameter.
4. Output STRICT JSON with structure:
{
  "parameter": "target_parameter_name",
  "finding": "Summary of bidder's capability/compliance claim",
  "extracted_value": 6.85,
  "extracted_unit": "Crores",
  "supporting_quote": "Exact verbatim sentence from evidence",
  "evidence_page": 2,
  "parameter_claims": [
     {"parameter": "target_parameter_name", "value": 6.85, "unit": "Crores", "document": "bid.pdf", "page": 2, "quote": "..."}
  ],
  "contradiction_detected": false,
  "contradiction_details": null,
  "is_ambiguous_or_missing": false,
  "confidence": 0.95
}
"""


def identify_target_parameter(clause: Union[Dict[str, Any], Any]) -> str:
    """Determine the canonical evaluation parameter for a clause."""
    rule_cfg = clause.get("rule_config") if isinstance(clause, dict) else getattr(clause, "rule_config", None) or {}
    param = rule_cfg.get("parameter") if isinstance(rule_cfg, dict) else None
    if param:
        p_lower = str(param).lower()
        if "turnover" in p_lower:
            return "turnover"
        if "local_content" in p_lower or "mii" in p_lower:
            if "self_cert" in p_lower:
                return "local_content_self_cert"
            return "local_content_percent"
        if "delivery" in p_lower:
            return "delivery_days"
        if "cpu" in p_lower or "core" in p_lower:
            return "cpu_cores"
        if "warranty" in p_lower:
            return "warranty_years"
        if "emd" in p_lower:
            return "emd_amount"
        if "contract" in p_lower or "experience" in p_lower:
            return "similar_contracts_count"
        return str(param)

    code = str(clause.get("clause_code") if isinstance(clause, dict) else getattr(clause, "clause_code", "")).lower()
    title = str(clause.get("title") if isinstance(clause, dict) else getattr(clause, "title", "")).lower()
    desc = str(clause.get("description") if isinstance(clause, dict) else getattr(clause, "description", "")).lower()
    cat = str(clause.get("category") if isinstance(clause, dict) else getattr(clause, "category", "")).lower()
    text = f"{code} {title} {desc} {cat}"

    if "turnover" in text or ("fin" in code and "01" in code):
        return "turnover"
    if "local content" in text or "mii" in text or "make in india" in text:
        if "self" in text or "cert" in text:
            return "local_content_self_cert"
        return "local_content_percent"
    if "delivery" in text:
        return "delivery_days"
    if "cpu" in text or "core" in text or "processor" in text or "server compute" in text:
        return "cpu_cores"
    if "warranty" in text:
        return "warranty_years"
    if "emd" in text or "earnest money" in text:
        return "emd_amount"
    if "contract" in text or "experience" in text:
        return "similar_contracts_count"
    if "bis" in text or "iso" in text:
        return "bis_and_iso_cert"

    return "general"


def _heuristic_evidence_interpreter(
    clause: Union[Dict[str, Any], Any],
    chunks: List[RetrievedEvidenceChunk],
) -> AIEvidenceInterpretation:
    """Deterministic, parameter-scoped fallback interpreter for offline execution and fast testing.

    Guarantees:
    - Evidence extraction is strictly scoped to the clause's target parameter.
    - Contradictions are detected ONLY between claims belonging to the same parameter.
    - An unrelated parameter discrepancy (e.g. local content) NEVER affects another parameter (e.g. CPU or delivery).
    """
    if not chunks:
        return AIEvidenceInterpretation(
            parameter="unknown",
            finding="No supporting evidence submitted by bidder for this requirement.",
            extracted_value=None,
            extracted_unit=None,
            supporting_quote="",
            evidence_page=1,
            parameter_claims=[],
            contradiction_detected=False,
            contradiction_details=None,
            is_ambiguous_or_missing=True,
            confidence=0.1,
        )

    target_param = identify_target_parameter(clause)
    top_chunk = chunks[0]
    claims: List[ParameterClaim] = []
    is_ambiguous = False
    best_quote = top_chunk.chunk_text[:200].strip()
    best_page = top_chunk.page_number
    best_chunk_id = top_chunk.chunk_id

    # 1. Parameter-scoped extraction
    if target_param == "turnover":
        for c in chunks:
            for m in re.finditer(r"turnover[^.\n]*?INR\s*([\d.]+)\s*Crores", c.chunk_text, re.IGNORECASE):
                claims.append(ParameterClaim(
                    parameter="turnover",
                    value=float(m.group(1)),
                    unit="Crores",
                    document=c.filename,
                    page=c.page_number,
                    chunk_id=c.chunk_id,
                    quote=m.group(0),
                ))
            for m in re.finditer(r"CA\s*Certificate.*?INR\s*([\d.]+)\s*Crores", c.chunk_text, re.IGNORECASE):
                claims.append(ParameterClaim(
                    parameter="turnover",
                    value=float(m.group(1)),
                    unit="Crores",
                    document=c.filename,
                    page=c.page_number,
                    chunk_id=c.chunk_id,
                    quote=m.group(0),
                ))
            if not any(cl.page == c.page_number for cl in claims) and "turnover" in c.chunk_text.lower():
                for m in re.finditer(r"INR\s*([\d.]+)\s*Crores", c.chunk_text, re.IGNORECASE):
                    prefix = c.chunk_text[max(0, m.start() - 35):m.start()].lower()
                    if "threshold" not in prefix and "required" not in prefix and "minimum" not in prefix:
                        claims.append(ParameterClaim(
                            parameter="turnover",
                            value=float(m.group(1)),
                            unit="Crores",
                            document=c.filename,
                            page=c.page_number,
                            chunk_id=c.chunk_id,
                            quote=m.group(0),
                        ))

    elif target_param == "local_content_percent":
        for c in chunks:
            for m in re.finditer(r"local\s*content[^.\n]*?(\d+)\s*(?:percent|%)", c.chunk_text, re.IGNORECASE):
                claims.append(ParameterClaim(
                    parameter="local_content_percent",
                    value=float(m.group(1)),
                    unit="%",
                    document=c.filename,
                    page=c.page_number,
                    chunk_id=c.chunk_id,
                    quote=m.group(0),
                ))
            for m in re.finditer(r"(\d+)\s*(?:percent|%)\s*(?:domestic\s*)?local\s*content", c.chunk_text, re.IGNORECASE):
                claims.append(ParameterClaim(
                    parameter="local_content_percent",
                    value=float(m.group(1)),
                    unit="%",
                    document=c.filename,
                    page=c.page_number,
                    chunk_id=c.chunk_id,
                    quote=m.group(0),
                ))

    elif target_param == "cpu_cores":
        for c in chunks:
            for m in re.finditer(r"(\d+)-core", c.chunk_text, re.IGNORECASE):
                claims.append(ParameterClaim(
                    parameter="cpu_cores",
                    value=float(m.group(1)),
                    unit="cores",
                    document=c.filename,
                    page=c.page_number,
                    chunk_id=c.chunk_id,
                    quote=m.group(0),
                ))
            if not any(cl.page == c.page_number for cl in claims):
                for m in re.finditer(r"(\d+)\s*cores?", c.chunk_text, re.IGNORECASE):
                    claims.append(ParameterClaim(
                        parameter="cpu_cores",
                        value=float(m.group(1)),
                        unit="cores",
                        document=c.filename,
                        page=c.page_number,
                        chunk_id=c.chunk_id,
                        quote=m.group(0),
                    ))

    elif target_param == "delivery_days":
        for c in chunks:
            for m in re.finditer(r"(?:within|require)\s*(\d+)\s*days", c.chunk_text, re.IGNORECASE):
                claims.append(ParameterClaim(
                    parameter="delivery_days",
                    value=float(m.group(1)),
                    unit="days",
                    document=c.filename,
                    page=c.page_number,
                    chunk_id=c.chunk_id,
                    quote=m.group(0),
                ))
            if not any(cl.page == c.page_number for cl in claims):
                for m in re.finditer(r"(\d+)\s*days\s*(?:delivery|timeline|installation|schedule)", c.chunk_text, re.IGNORECASE):
                    claims.append(ParameterClaim(
                        parameter="delivery_days",
                        value=float(m.group(1)),
                        unit="days",
                        document=c.filename,
                        page=c.page_number,
                        chunk_id=c.chunk_id,
                        quote=m.group(0),
                    ))

    elif target_param == "warranty_years":
        for c in chunks:
            for m in re.finditer(r"warranty\s*of\s*(\d+)\s*years?", c.chunk_text, re.IGNORECASE):
                claims.append(ParameterClaim(
                    parameter="warranty_years",
                    value=float(m.group(1)),
                    unit="years",
                    document=c.filename,
                    page=c.page_number,
                    chunk_id=c.chunk_id,
                    quote=m.group(0),
                ))
            if not any(cl.page == c.page_number for cl in claims):
                for m in re.finditer(r"(\d+)\s*years?\s*warranty", c.chunk_text, re.IGNORECASE):
                    claims.append(ParameterClaim(
                        parameter="warranty_years",
                        value=float(m.group(1)),
                        unit="years",
                        document=c.filename,
                        page=c.page_number,
                        chunk_id=c.chunk_id,
                        quote=m.group(0),
                    ))
            if "optional" in c.chunk_text.lower() and "extension" in c.chunk_text.lower():
                is_ambiguous = True

    elif target_param == "emd_amount":
        for c in chunks:
            for m in re.finditer(r"INR\s*([\d,]+)\s*(?:via|towards|online|challan)", c.chunk_text, re.IGNORECASE):
                raw = m.group(1).replace(",", "")
                try:
                    claims.append(ParameterClaim(
                        parameter="emd_amount",
                        value=float(raw),
                        unit="INR",
                        document=c.filename,
                        page=c.page_number,
                        chunk_id=c.chunk_id,
                        quote=m.group(0),
                    ))
                except ValueError:
                    pass

    elif target_param == "similar_contracts_count":
        for c in chunks:
            for m in re.finditer(
                r"(?:executed|completed|awarded|performed|references)\s*(?:only\s*)?(\d+)\s+[\w\s]{0,40}?contracts?",
                c.chunk_text,
                re.IGNORECASE,
            ):
                claims.append(ParameterClaim(
                    parameter="similar_contracts_count",
                    value=float(m.group(1)),
                    unit="contracts",
                    document=c.filename,
                    page=c.page_number,
                    chunk_id=c.chunk_id,
                    quote=m.group(0),
                ))

    elif target_param in ("bis_and_iso_cert", "bis_certificate", "iso_9001_certificate"):
        for c in chunks:
            c_low = c.chunk_text.lower()
            if "pending" in c_low or "expired" in c_low:
                is_ambiguous = True
            if "certified" in c_low or "compliant" in c_low or "registration" in c_low:
                claims.append(ParameterClaim(
                    parameter=target_param,
                    value=True,
                    unit="status",
                    document=c.filename,
                    page=c.page_number,
                    chunk_id=c.chunk_id,
                    quote=c.chunk_text[:150],
                ))

    # 2. Strict parameter-scoped contradiction check
    contradiction_detected = False
    contradiction_details = None
    numeric_vals = [c.value for c in claims if isinstance(c.value, (int, float))]
    unique_vals = sorted(list(set(numeric_vals)))

    if len(unique_vals) > 1:
        contradiction_detected = True
        contradiction_details = (
            f"Cross-chunk contradiction detected for parameter '{target_param}': "
            f"Bidder document contains conflicting values: {unique_vals}."
        )

    # 3. Resolve extracted value
    extracted_val = None
    extracted_unit = None
    if claims:
        preferred = claims[0]
        if target_param == "turnover":
            ca_c = [cl for cl in claims if "ca" in cl.quote.lower()]
            if ca_c:
                preferred = ca_c[0]
        extracted_val = preferred.value
        extracted_unit = preferred.unit
        best_quote = preferred.quote or top_chunk.chunk_text[:200]
        best_page = preferred.page
        best_chunk_id = preferred.chunk_id

    if contradiction_detected:
        finding_summary = f"Conflicting values detected for {target_param}: {unique_vals}."
    elif extracted_val is not None:
        finding_summary = f"Extracted {target_param}: {extracted_val} {extracted_unit or ''}."
    else:
        finding_summary = f"No measurable evidence found for parameter '{target_param}' across {len(chunks)} chunks."

    confidence = 0.90 if not contradiction_detected and not is_ambiguous else 0.40

    return AIEvidenceInterpretation(
        parameter=target_param,
        finding=finding_summary,
        extracted_value=extracted_val,
        extracted_unit=extracted_unit,
        supporting_quote=best_quote,
        evidence_page=best_page,
        evidence_chunk_id=best_chunk_id,
        parameter_claims=claims,
        contradiction_detected=contradiction_detected,
        contradiction_details=contradiction_details,
        is_ambiguous_or_missing=is_ambiguous,
        confidence=confidence,
    )


async def interpret_evidence_for_clause(
    clause: Union[Dict[str, Any], Any],
    evidence_chunks: List[RetrievedEvidenceChunk],
    use_live_llm: bool = False,
) -> AIEvidenceInterpretation:
    """Interpret evidence chunks for a clause using either live NVIDIA NIM LLM or deterministic fallback."""
    if not evidence_chunks:
        return AIEvidenceInterpretation(
            parameter="unknown",
            finding="No relevant evidence chunks retrieved for this clause.",
            extracted_value=None,
            extracted_unit=None,
            supporting_quote="",
            evidence_page=1,
            parameter_claims=[],
            contradiction_detected=False,
            contradiction_details=None,
            is_ambiguous_or_missing=True,
            confidence=0.0,
        )

    target_param = identify_target_parameter(clause)

    # Use live LLM if explicitly requested
    if use_live_llm:
        client = get_nvidia_client()
        if client.is_configured:
            title = clause.get("title") if isinstance(clause, dict) else getattr(clause, "title", "")
            desc = clause.get("description") if isinstance(clause, dict) else getattr(clause, "description", "")
            src = clause.get("source_text") if isinstance(clause, dict) else getattr(clause, "source_text", "")

            evidence_context = "\n\n".join(
                f"[Page {c.page_number} - {c.filename}]: {c.chunk_text}" for c in evidence_chunks
            )

            prompt = (
                f"Target Parameter: {target_param}\n"
                f"Tender Clause Title: {title}\n"
                f"Description: {desc}\n"
                f"Tender Source Text: {src}\n\n"
                f"Retrieved Bidder Evidence Chunks:\n{evidence_context}\n\n"
                f"Analyze the evidence chunks specifically for the target parameter '{target_param}' and return the JSON assessment."
            )

            try:
                res = await client.structured_completion(
                    prompt=prompt,
                    system_prompt=INTERPRETATION_SYSTEM_PROMPT,
                    temperature=0.0,
                    max_tokens=1024,
                    timeout=30.0,
                )
                if isinstance(res, dict) and "finding" in res:
                    raw_claims = res.get("parameter_claims") or []
                    parsed_claims = []
                    for rc in raw_claims:
                        if isinstance(rc, dict):
                            parsed_claims.append(ParameterClaim(
                                parameter=rc.get("parameter", target_param),
                                value=rc.get("value"),
                                unit=rc.get("unit"),
                                document=rc.get("document", evidence_chunks[0].filename),
                                page=rc.get("page", evidence_chunks[0].page_number),
                                chunk_id=rc.get("chunk_id", evidence_chunks[0].chunk_id),
                                quote=rc.get("quote", ""),
                            ))

                    return AIEvidenceInterpretation(
                        parameter=target_param,
                        finding=res.get("finding", "Evidence interpreted."),
                        extracted_value=res.get("extracted_value"),
                        extracted_unit=res.get("extracted_unit"),
                        supporting_quote=res.get("supporting_quote", ""),
                        evidence_page=res.get("evidence_page", evidence_chunks[0].page_number),
                        evidence_chunk_id=evidence_chunks[0].chunk_id,
                        parameter_claims=parsed_claims,
                        contradiction_detected=bool(res.get("contradiction_detected", False)),
                        contradiction_details=res.get("contradiction_details"),
                        is_ambiguous_or_missing=bool(res.get("is_ambiguous_or_missing", False)),
                        confidence=float(res.get("confidence", 0.85)),
                    )
            except Exception as e:
                logger.warning(f"Live LLM evidence interpretation failed ({e}); falling back to heuristic interpreter.")

    # High-precision deterministic fallback
    return _heuristic_evidence_interpreter(clause, evidence_chunks)
