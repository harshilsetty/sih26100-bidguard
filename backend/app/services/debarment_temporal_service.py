"""Debarment Temporal Evaluation Service.

Phase 8.2 — SIH26100 Time-Aware Debarment Verification.
Evaluates debarment applicability on a specified as_of_date using deterministic,
inclusive interval arithmetic and strict open-ended semantics.

LOCKED TEMPORAL SEMANTICS:
- ACTIVE_ON_DATE     -> is_debarred_on_date = True
- EXPIRED_BEFORE_DATE -> is_debarred_on_date = False
- STARTS_AFTER_DATE   -> is_debarred_on_date = False
- UNKNOWN_PERIOD      -> is_debarred_on_date = False

INCLUSIVE INTERVAL:
start_date <= as_of_date <= end_date

OPEN-ENDED RECORDS:
Active ONLY when status is explicitly:
ACTIVE_INDEFINITE or PERMANENT.
Never infer active status merely because end_date is NULL.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Union
import logging

from app.schemas.statutory_verification import DebarmentTemporalStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DebarmentTemporalEvaluation:
    """Result of temporal debarment evaluation against an as_of_date."""
    temporal_status: DebarmentTemporalStatus
    is_debarred_on_date: bool
    as_of_date: Optional[date]
    start_date: Optional[date]
    end_date: Optional[date]
    reason: str


class DebarmentTemporalService:
    """Pure, deterministic temporal evaluation logic for debarment records."""

    @staticmethod
    def parse_date(val: Optional[Union[str, date, datetime]]) -> Optional[date]:
        """Safely parse input date into datetime.date."""
        if val is None:
            return None
        if isinstance(val, date) and not isinstance(val, datetime):
            return val
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, str):
            val_clean = val.strip()
            if not val_clean or val_clean.upper() in ("NONE", "NULL", ""):
                return None
            try:
                # Handle YYYY-MM-DD or ISO strings
                if "T" in val_clean:
                    return datetime.fromisoformat(val_clean.replace("Z", "+00:00")).date()
                return date.fromisoformat(val_clean[:10])
            except Exception as err:
                logger.warning(f"Failed to parse date string '{val}': {err}")
                return None
        return None

    @classmethod
    def evaluate(
        cls,
        as_of: Optional[Union[str, date, datetime]],
        start: Optional[Union[str, date, datetime]],
        end: Optional[Union[str, date, datetime]],
        status: Optional[str] = None,
    ) -> DebarmentTemporalEvaluation:
        """Evaluate debarment status against as_of_date.

        Args:
            as_of: Reference date (bid submission date or evaluation date).
            start: Debarment order start date.
            end: Debarment order end date.
            status: Source-reported status string (e.g. ACTIVE, EXPIRED, ACTIVE_INDEFINITE, PERMANENT, REVOKED).
        """
        ref_date = cls.parse_date(as_of)
        start_d = cls.parse_date(start)
        end_d = cls.parse_date(end)

        # Locked requirement: as_of_date is None -> UNKNOWN_PERIOD, False
        if ref_date is None:
            return DebarmentTemporalEvaluation(
                temporal_status=DebarmentTemporalStatus.UNKNOWN_PERIOD,
                is_debarred_on_date=False,
                as_of_date=None,
                start_date=start_d,
                end_date=end_d,
                reason="No as_of_date provided for temporal comparison.",
            )

        norm_status = (status or "").strip().upper()

        # 1. Explicit revocation check: Revoked orders do not constitute active debarment
        if norm_status == "REVOKED":
            return DebarmentTemporalEvaluation(
                temporal_status=DebarmentTemporalStatus.EXPIRED_BEFORE_DATE,
                is_debarred_on_date=False,
                as_of_date=ref_date,
                start_date=start_d,
                end_date=end_d,
                reason="Debarment order has been explicitly REVOKED by competent authority.",
            )

        # 2. Open-ended evaluation (end_date is NULL)
        if end_d is None:
            if norm_status in ("ACTIVE_INDEFINITE", "PERMANENT"):
                if start_d is not None and ref_date < start_d:
                    return DebarmentTemporalEvaluation(
                        temporal_status=DebarmentTemporalStatus.STARTS_AFTER_DATE,
                        is_debarred_on_date=False,
                        as_of_date=ref_date,
                        start_date=start_d,
                        end_date=None,
                        reason=f"Open-ended debarment ({norm_status}) commences on future date {start_d.isoformat()}.",
                    )
                return DebarmentTemporalEvaluation(
                    temporal_status=DebarmentTemporalStatus.ACTIVE_ON_DATE,
                    is_debarred_on_date=True,
                    as_of_date=ref_date,
                    start_date=start_d,
                    end_date=None,
                    reason=f"Debarment is open-ended with explicit status {norm_status} active on {ref_date.isoformat()}.",
                )
            # Never infer active status merely because end_date is NULL with ordinary/unspecified status
            return DebarmentTemporalEvaluation(
                temporal_status=DebarmentTemporalStatus.UNKNOWN_PERIOD,
                is_debarred_on_date=False,
                as_of_date=ref_date,
                start_date=start_d,
                end_date=None,
                reason=f"End date is unspecified and status '{norm_status or 'UNSPECIFIED'}' is neither ACTIVE_INDEFINITE nor PERMANENT.",
            )

        # 3. Missing start date with an end date specified
        if start_d is None:
            if ref_date > end_d:
                return DebarmentTemporalEvaluation(
                    temporal_status=DebarmentTemporalStatus.EXPIRED_BEFORE_DATE,
                    is_debarred_on_date=False,
                    as_of_date=ref_date,
                    start_date=None,
                    end_date=end_d,
                    reason=f"Debarment concluded on {end_d.isoformat()}, prior to evaluation date {ref_date.isoformat()}.",
                )
            return DebarmentTemporalEvaluation(
                temporal_status=DebarmentTemporalStatus.UNKNOWN_PERIOD,
                is_debarred_on_date=False,
                as_of_date=ref_date,
                start_date=None,
                end_date=end_d,
                reason=f"Start date is unspecified; cannot deterministically verify if debarment commenced prior to {ref_date.isoformat()}.",
            )

        # 4. Both start_d and end_d are present: Inclusive interval check
        # start_d <= ref_date <= end_d
        if ref_date < start_d:
            return DebarmentTemporalEvaluation(
                temporal_status=DebarmentTemporalStatus.STARTS_AFTER_DATE,
                is_debarred_on_date=False,
                as_of_date=ref_date,
                start_date=start_d,
                end_date=end_d,
                reason=f"Debarment commences on future date {start_d.isoformat()} (as of {ref_date.isoformat()}).",
            )

        if ref_date > end_d:
            return DebarmentTemporalEvaluation(
                temporal_status=DebarmentTemporalStatus.EXPIRED_BEFORE_DATE,
                is_debarred_on_date=False,
                as_of_date=ref_date,
                start_date=start_d,
                end_date=end_d,
                reason=f"Debarment period expired on {end_d.isoformat()} (prior to {ref_date.isoformat()}).",
            )

        # start_d <= ref_date <= end_d (inclusive of endpoints)
        return DebarmentTemporalEvaluation(
            temporal_status=DebarmentTemporalStatus.ACTIVE_ON_DATE,
            is_debarred_on_date=True,
            as_of_date=ref_date,
            start_date=start_d,
            end_date=end_d,
            reason=f"Debarment is actively in force on {ref_date.isoformat()} (effective {start_d.isoformat()} to {end_d.isoformat()}).",
        )
