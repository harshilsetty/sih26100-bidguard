import logging
from typing import Optional, Union, Dict, Any
from app.schemas.evaluation import DeterministicRuleResult
from app.schemas.clause import RuleType

logger = logging.getLogger(__name__)


def normalize_numeric_value(val: Any) -> Optional[float]:
    """Safely convert various value types (str, int, float) into a float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        # Remove commas, currency symbols, percentage signs
        cleaned = val.replace(",", "").replace("INR", "").replace("₹", "").replace("%", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def evaluate_numeric_min(
    actual: Optional[float],
    required: Optional[float],
    parameter: Optional[str] = None,
    unit: Optional[str] = None,
) -> DeterministicRuleResult:
    """Deterministic check: actual >= required (NUMERIC_MIN)."""
    if required is None:
        return DeterministicRuleResult(
            rule_type=RuleType.NUMERIC_MIN.value,
            parameter=parameter,
            required_value=required,
            actual_value=actual,
            unit=unit,
            passed=None,
            margin=None,
            message="Required threshold value is missing or unconfigured.",
        )

    if actual is None:
        return DeterministicRuleResult(
            rule_type=RuleType.NUMERIC_MIN.value,
            parameter=parameter,
            required_value=required,
            actual_value=None,
            unit=unit,
            passed=False,
            margin=None,
            message=f"No measurable value extracted from evidence for {parameter or 'criterion'} (required minimum: {required} {unit or ''}).",
        )

    passed = actual >= required
    margin = round(actual - required, 4)
    unit_str = f" {unit}" if unit else ""

    if passed:
        msg = f"Satisfied: actual {actual}{unit_str} meets/exceeds required minimum {required}{unit_str} (surplus: +{margin}{unit_str})."
    else:
        deficit = round(abs(margin), 4)
        msg = f"Deficit: actual {actual}{unit_str} is below required minimum {required}{unit_str} (shortfall: -{deficit}{unit_str})."

    return DeterministicRuleResult(
        rule_type=RuleType.NUMERIC_MIN.value,
        parameter=parameter,
        required_value=required,
        actual_value=actual,
        unit=unit,
        passed=passed,
        margin=margin,
        message=msg,
    )


def evaluate_numeric_max(
    actual: Optional[float],
    required: Optional[float],
    parameter: Optional[str] = None,
    unit: Optional[str] = None,
) -> DeterministicRuleResult:
    """Deterministic check: actual <= required (NUMERIC_MAX, e.g. delivery days or SLA penalty cap)."""
    if required is None:
        return DeterministicRuleResult(
            rule_type=RuleType.NUMERIC_MAX.value,
            parameter=parameter,
            required_value=required,
            actual_value=actual,
            unit=unit,
            passed=None,
            margin=None,
            message="Required maximum ceiling value is missing or unconfigured.",
        )

    if actual is None:
        return DeterministicRuleResult(
            rule_type=RuleType.NUMERIC_MAX.value,
            parameter=parameter,
            required_value=required,
            actual_value=None,
            unit=unit,
            passed=False,
            margin=None,
            message=f"No measurable value extracted from evidence for {parameter or 'criterion'} (maximum ceiling: {required} {unit or ''}).",
        )

    passed = actual <= required
    margin = round(required - actual, 4)
    unit_str = f" {unit}" if unit else ""

    if passed:
        msg = f"Satisfied: actual {actual}{unit_str} is within required ceiling {required}{unit_str} (buffer: {margin}{unit_str})."
    else:
        overage = round(actual - required, 4)
        msg = f"Exceeded: actual {actual}{unit_str} exceeds allowed maximum ceiling {required}{unit_str} (excess: +{overage}{unit_str})."

    return DeterministicRuleResult(
        rule_type=RuleType.NUMERIC_MAX.value,
        parameter=parameter,
        required_value=required,
        actual_value=actual,
        unit=unit,
        passed=passed,
        margin=margin,
        message=msg,
    )


def evaluate_document_required(
    doc_parameter: Optional[str],
    evidence_text: str,
    explicitly_found: bool = True,
) -> DeterministicRuleResult:
    """Deterministic check: required certificate / documentation is verified in evidence."""
    param_name = doc_parameter or "required_document"
    if explicitly_found and evidence_text:
        return DeterministicRuleResult(
            rule_type=RuleType.DOCUMENT_REQUIRED.value,
            parameter=param_name,
            required_value="DOCUMENT_SUBMITTED",
            actual_value="FOUND_IN_EVIDENCE",
            unit="DOC",
            passed=True,
            margin=0.0,
            message=f"Required documentation '{param_name}' is confirmed present in bidder submission.",
        )
    else:
        return DeterministicRuleResult(
            rule_type=RuleType.DOCUMENT_REQUIRED.value,
            parameter=param_name,
            required_value="DOCUMENT_SUBMITTED",
            actual_value="NOT_FOUND",
            unit="DOC",
            passed=False,
            margin=-1.0,
            message=f"Required documentation '{param_name}' was not confirmed in evidence.",
        )


def evaluate_deterministic_rule(
    rule_config: Optional[Dict[str, Any]],
    extracted_value: Any,
    evidence_text: str = "",
) -> DeterministicRuleResult:
    """Dispatcher to evaluate a structured rule_config deterministically in pure Python."""
    if not rule_config or not isinstance(rule_config, dict):
        return DeterministicRuleResult(
            rule_type=RuleType.CUSTOM.value,
            passed=None,
            message="No structured deterministic rule configured; requires qualitative human verification.",
        )

    rule_type_raw = rule_config.get("type", "CUSTOM")
    if hasattr(rule_type_raw, "value"):
        rule_type = rule_type_raw.value
    else:
        rule_type = str(rule_type_raw).upper()

    param = rule_config.get("parameter")
    req_val = normalize_numeric_value(rule_config.get("value"))
    unit = rule_config.get("unit")
    act_val = normalize_numeric_value(extracted_value)

    if rule_type in (RuleType.NUMERIC_MIN.value, RuleType.PERCENT_MIN.value):
        return evaluate_numeric_min(actual=act_val, required=req_val, parameter=param, unit=unit)

    elif rule_type in (RuleType.NUMERIC_MAX.value, "PERCENT_MAX"):
        return evaluate_numeric_max(actual=act_val, required=req_val, parameter=param, unit=unit)

    elif rule_type in ("NUMERIC_EXACT", "EXACT"):
        if req_val is None or act_val is None:
            return DeterministicRuleResult(
                rule_type="NUMERIC_EXACT",
                parameter=param,
                required_value=req_val,
                actual_value=act_val,
                unit=unit,
                passed=False,
                message="Value missing for exact numeric comparison.",
            )
        passed = (act_val == req_val)
        return DeterministicRuleResult(
            rule_type="NUMERIC_EXACT",
            parameter=param,
            required_value=req_val,
            actual_value=act_val,
            unit=unit,
            passed=passed,
            margin=round(act_val - req_val, 4),
            message=f"Exact match check: actual {act_val} {'==' if passed else '!='} required {req_val}.",
        )

    elif rule_type == RuleType.DOCUMENT_REQUIRED.value:
        doc_present = False
        if act_val is not None and act_val is not False:
            doc_present = True
        elif evidence_text:
            ev_low = evidence_text.lower()
            p_low = str(param or "").lower()
            if "bis" in p_low or "iso" in p_low:
                doc_present = (("bis" in ev_low or "iso" in ev_low) and ("cert" in ev_low or "standard" in ev_low or "compliant" in ev_low))
            elif "balance" in p_low or "audit" in p_low:
                doc_present = any(w in ev_low for w in ["balance sheet", "audited", "ca certificate", "udin"])
            elif "local_content" in p_low:
                doc_present = any(w in ev_low for w in ["self-cert", "self cert", "declaration", "local supplier"])
            elif "insolvency" in p_low:
                doc_present = any(w in ev_low for w in ["insolvency", "bankruptcy", "undertaking"])
            elif "mse" in p_low:
                doc_present = any(w in ev_low for w in ["mse", "msme", "udyam", "exemption"])
            else:
                doc_present = any(w in ev_low for w in ["uploaded", "submitted", "enclosed", "certified", "attached", "certificate"])
        return evaluate_document_required(doc_parameter=param, evidence_text=evidence_text, explicitly_found=doc_present)

    elif rule_type in (RuleType.BOOLEAN_CERT.value, "BOOLEAN_TRUE"):
        passed = bool(extracted_value is True or str(extracted_value).lower() in ("true", "yes", "complied", "agreed"))
        return DeterministicRuleResult(
            rule_type=RuleType.BOOLEAN_CERT.value,
            parameter=param,
            required_value=True,
            actual_value=extracted_value,
            passed=passed,
            message=f"Affirmative condition check: {'Satisfied' if passed else 'Failed'}.",
        )

    else:
        return DeterministicRuleResult(
            rule_type=rule_type,
            parameter=param,
            required_value=rule_config.get("value"),
            actual_value=extracted_value,
            unit=unit,
            passed=None,
            message="Custom or qualitative rule: requires human procurement officer confirmation.",
        )
