"""Deterministic Synthetic Government Dataset Generator.

Phase 6.2 — SIH26100 Mock Integrated Verification Foundation.
Generates exactly 1,000 deterministic records for each of the 5 sources:
1. GSTN (~1,000)
2. Udyam (~1,000)
3. MCA (~1,000)
4. Income Tax (~1,000)
5. Make in India / Local Content (~1,000)
Total: exactly 5,000 records.

Includes deterministic identity mappings for 10 showcase bidders (BIDDER-01 to BIDDER-10)
and the 5 critical contradiction / demonstration fixtures.
Seed: 26100 (deterministic & reproducible).
"""

import os
import json
import random
from typing import Dict, Any, List, Tuple
from datetime import datetime, timezone, timedelta

SEED = 26100
MOCK_SOURCE_TYPE_LABEL = "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"
BASE_TIMESTAMP = "2026-03-01T10:00:00Z"

INDIAN_STATES = [
    ("DL", "Delhi", "07"),
    ("MH", "Maharashtra", "27"),
    ("KA", "Karnataka", "29"),
    ("TN", "Tamil Nadu", "33"),
    ("TS", "Telangana", "36"),
    ("UP", "Uttar Pradesh", "09"),
    ("GJ", "Gujarat", "24"),
    ("WB", "West Bengal", "19"),
    ("RJ", "Rajasthan", "08"),
    ("HR", "Haryana", "06"),
]

ENTERPRISE_PREFIXES = [
    "Apex", "Zenith", "Quantum", "Bharat", "Indo", "Vanguard", "Trident", "Pinnacle",
    "Alpha", "Sigma", "Matrix", "Cyber", "Nova", "Paramount", "Titan", "Spectra",
    "Aura", "Omicron", "Nexus", "Infiniti", "Global", "Sterling", "Kavach", "Garuda"
]

ENTERPRISE_CORE = [
    "Technologies", "Infotech", "Systems", "Solutions", "Enterprises", "Networks",
    "Digital", "Hardware", "Computing", "Electronics", "Instruments", "Software",
    "Innovations", "Scientific", "Dynamics", "Engineering", "Data Systems", "Consulting"
]

# ---------------------------------------------------------------------------
# 10 SHOWCASE BIDDER PROFILES
# ---------------------------------------------------------------------------

SHOWCASE_BIDDERS_CONFIG: List[Dict[str, Any]] = [
    {
        "entity_identifier": "BIDDER-01",
        "company_name": "Enterprise Tech Solutions Ltd",
        "state_code": "MH",
        "pan": "AAACE1001A",
        "gstin": "27AAACE1001A1Z1",
        "udyam": "UDYAM-MH-01-0010001",
        "cin": "U72200MH2015PLC261001",
        "gstn_turnover": 45.20,
        "gstn_status": "ACTIVE",
        "udyam_type": "MEDIUM",
        "udyam_status": "ACTIVE",
        "mca_status": "ACTIVE",
        "mca_name": "Enterprise Tech Solutions Ltd",
        "it_status": "ACTIVE",
        "mii_content": 62.0,
        "mii_status": "VERIFIED_CLASS_I",
        "profile": "Excellent / highly compliant enterprise",
    },
    {
        "entity_identifier": "BIDDER-02",
        "company_name": "Bharat Server Systems Pvt Ltd",
        "state_code": "DL",
        "pan": "AABCB1002B",
        "gstin": "07AABCB1002B1Z2",
        "udyam": "UDYAM-DL-01-0010002",
        "cin": "U72900DL2017PTC261002",
        "gstn_turnover": 38.50,
        "gstn_status": "ACTIVE",
        "udyam_type": "SMALL",
        "udyam_status": "ACTIVE",
        "mca_status": "ACTIVE",
        "mca_name": "Bharat Server Systems Pvt Ltd",
        "it_status": "ACTIVE",
        "mii_content": 58.0,
        "mii_status": "VERIFIED_CLASS_I",
        "profile": "Excellent / highly compliant enterprise",
    },
    {
        "entity_identifier": "BIDDER-03",
        "company_name": "Zenith Cloud Technologies Pvt Ltd",
        "state_code": "KA",
        "pan": "AABCZ1003C",
        "gstin": "29AABCZ1003C1Z3",
        "udyam": "UDYAM-KR-03-0010003",
        "cin": "U72900KA2020PTC261003",
        "gstn_turnover": 18.20,
        "gstn_status": "ACTIVE",
        # SCENARIO 2 — MSE EXEMPTION
        "udyam_type": "MICRO",
        "udyam_status": "ACTIVE",
        "mca_status": "ACTIVE",
        "mca_name": "Zenith Cloud Technologies Pvt Ltd",
        "it_status": "ACTIVE",
        "mii_content": 54.0,
        "mii_status": "VERIFIED_CLASS_I",
        "profile": "Strong / MSE Exemption supporting evidence",
    },
    {
        "entity_identifier": "BIDDER-04",
        "company_name": "Alpha Technologies Pvt Ltd",
        "state_code": "TS",
        "pan": "AABCA1004D",
        "gstin": "36AABCA1004D1Z4",
        "udyam": "UDYAM-TS-01-0010004",
        "cin": "U72200TG2018PTC261004",
        "gstn_turnover": 24.50,
        "gstn_status": "ACTIVE",
        "udyam_type": "SMALL",
        "udyam_status": "ACTIVE",
        "mca_status": "ACTIVE",
        # SCENARIO 4 — ENTITY NAME VARIATION
        "mca_name": "Alpha Technology Private Limited",
        "it_status": "ACTIVE",
        "mii_content": 51.5,
        "mii_status": "VERIFIED_CLASS_I",
        "profile": "Strong with minor entity-name variation in MCA",
    },
    {
        "entity_identifier": "BIDDER-05",
        "company_name": "Quantum Infrastructure Networks Ltd",
        "state_code": "TN",
        "pan": "AABCQ1005E",
        "gstin": "33AABCQ1005E1Z5",
        "udyam": "UDYAM-TN-02-0010005",
        "cin": "U72900TN2016PLC261005",
        "gstn_turnover": 5.10,
        "gstn_status": "ACTIVE",
        "udyam_type": "MEDIUM",
        "udyam_status": "ACTIVE",
        "mca_status": "ACTIVE",
        "mca_name": "Quantum Infrastructure Networks Ltd",
        "it_status": "ACTIVE",
        "mii_content": 55.0,
        "mii_status": "VERIFIED_CLASS_I",
        "profile": "Good technical but financial turnover border-line concern",
    },
    {
        "entity_identifier": "BIDDER-06",
        "company_name": "Pinnacle Computing Solutions Pvt Ltd",
        "state_code": "GJ",
        "pan": "AABCP1006F",
        "gstin": "24AABCP1006F1Z6",
        "udyam": "UDYAM-GJ-01-0010006",
        "cin": "U72900GJ2019PTC261006",
        "gstn_turnover": 12.40,
        "gstn_status": "ACTIVE",
        "udyam_type": "SMALL",
        "udyam_status": "ACTIVE",
        "mca_status": "ACTIVE",
        "mca_name": "Pinnacle Computing Solutions Pvt Ltd",
        "it_status": "ACTIVE",
        "mii_content": 52.0,
        "mii_status": "VERIFIED_CLASS_I",
        "profile": "Moderate compliance vendor",
    },
    {
        "entity_identifier": "BIDDER-07",
        "company_name": "Trident Hardware & Services Ltd",
        "state_code": "WB",
        "pan": "AABCT1007G",
        "gstin": "19AABCT1007G1Z7",
        "udyam": "UDYAM-WB-01-0010007",
        "cin": "U72200WB2014PLC261007",
        "gstn_turnover": 15.60,
        "gstn_status": "ACTIVE",
        "udyam_type": "MEDIUM",
        "udyam_status": "ACTIVE",
        "mca_status": "ACTIVE",
        "mca_name": "Trident Hardware & Services Ltd",
        "it_status": "ACTIVE",
        "mii_content": 42.0,
        "mii_status": "VERIFIED_CLASS_II",
        "profile": "Multiple missing evidence cases / Class II local content",
    },
    {
        "entity_identifier": "BIDDER-08",
        "company_name": "Vanguard Electronic Systems Pvt Ltd",
        "state_code": "UP",
        "pan": "AABCV1008H",
        "gstin": "09AABCV1008H1Z8",
        "udyam": "UDYAM-UP-01-0010008",
        "cin": "U72900UP2013PTC261008",
        "gstn_turnover": 6.80,
        # SCENARIO 5 — INVALID / INACTIVE STATUS
        "gstn_status": "CANCELLED",
        "udyam_type": "SMALL",
        "udyam_status": "SUSPENDED",
        "mca_status": "UNDER_LIQUIDATION",
        "mca_name": "Vanguard Electronic Systems Pvt Ltd",
        "it_status": "INOPERATIVE",
        "mii_content": 28.0,
        "mii_status": "NON_LOCAL",
        "profile": "Statutory problems / Inactive or cancelled external status",
    },
    {
        "entity_identifier": "BIDDER-09",
        "company_name": "Legacy Hardware Trading Co",
        "state_code": "DL",
        "pan": "AABCL1009I",
        "gstin": "07AABCL1009I1Z9",
        "udyam": "UDYAM-DL-02-0010009",
        "cin": "U72200DL2012PTC261009",
        "gstn_turnover": 4.80,  # Below ₹10 Cr / ₹5 Cr threshold
        "gstn_status": "ACTIVE",
        "udyam_type": "SMALL",
        "udyam_status": "ACTIVE",
        "mca_status": "ACTIVE",
        "mca_name": "Legacy Hardware Trading Co",
        "it_status": "ACTIVE",
        "mii_content": 30.0,
        "mii_status": "NON_LOCAL",
        "profile": "Major technical and financial failure vendor",
    },
    {
        "entity_identifier": "BIDDER-10",
        "company_name": "Apex System Integrators Pvt Ltd",
        "state_code": "KA",
        "pan": "AABCA1010J",
        "gstin": "29AABCA1010J1Z0",
        "udyam": "UDYAM-KR-02-0010010",
        "cin": "U72900KA2017PTC261010",
        # SCENARIO 1 — TURNOVER CONTRADICTION (Bidder claims ₹8 Cr vs GSTN ₹3.65 Cr)
        "gstn_turnover": 3.65,
        "gstn_status": "ACTIVE",
        "udyam_type": "SMALL",
        "udyam_status": "ACTIVE",
        "mca_status": "ACTIVE",
        "mca_name": "Apex System Integrators Pvt Ltd",
        "it_status": "ACTIVE",
        # SCENARIO 3 — LOCAL CONTENT CONTRADICTION (Bidder claims 50%, BOM 32%, MII 32%)
        "mii_content": 32.0,
        "mii_status": "CONTRADICTION",
        "profile": "Multiple cross-source contradictions (Turnover & Local Content)",
    },
]


def _deterministic_pan(rng: random.Random, idx: int) -> str:
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    prefix = "".join(rng.choices(letters, k=5))
    number = f"{1000 + (idx % 9000):04d}"
    suffix = rng.choice(letters)
    return f"{prefix}{number}{suffix}"


def _deterministic_gstin(rng: random.Random, pan: str, state_num: str, idx: int) -> str:
    entity_code = str((idx % 9) + 1)
    checksum = rng.choice("0123456789ABCDEFGHJKLMNPQRSTUVWXYZ")
    return f"{state_num}{pan}{entity_code}Z{checksum}"


def _deterministic_cin(rng: random.Random, state_code: str, year: int, idx: int) -> str:
    sub = "PTC" if idx % 2 == 0 else "PLC"
    return f"U{72000 + (idx % 999):05d}{state_code}{year}{sub}{100000 + idx:06d}"


def generate_mock_datasets() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Generate deterministic synthetic datasets for all 5 domains."""
    rng = random.Random(SEED)

    gstn_records: List[Dict[str, Any]] = []
    udyam_records: List[Dict[str, Any]] = []
    mca_records: List[Dict[str, Any]] = []
    it_records: List[Dict[str, Any]] = []
    mii_records: List[Dict[str, Any]] = []

    # -----------------------------------------------------------------------
    # Step 1: Ingest 10 Showcase Bidders with fixed scenario values
    # -----------------------------------------------------------------------
    for b in SHOWCASE_BIDDERS_CONFIG:
        e_id = b["entity_identifier"]
        s_code = b["state_code"]
        state_name = next(s[1] for s in INDIAN_STATES if s[0] == s_code)
        
        # 1. GSTN
        gstn_records.append({
            "verification_id": f"MOCK-GSTN-{e_id}",
            "source": "GSTN",
            "entity_identifier": e_id,
            "status": b["gstn_status"],
            "gstin": b["gstin"],
            "legal_name": b["company_name"],
            "registration_status": b["gstn_status"],
            "registration_date": "2018-07-01",
            "state": state_name,
            "verified_turnover": b["gstn_turnover"],
            "taxpayer_type": "Regular",
            "filing_status": "UP_TO_DATE" if b["gstn_status"] == "ACTIVE" else "DEFICIENT",
            "verified_fields": {
                "gstin": b["gstin"],
                "annual_turnover_cr": b["gstn_turnover"],
                "status": b["gstn_status"],
            },
            "verification_timestamp": BASE_TIMESTAMP,
            "raw_response": {
                "source": "GSTN_API_SIMULATOR",
                "retrieved_turnover": b["gstn_turnover"],
                "is_active": b["gstn_status"] == "ACTIVE",
            },
            "is_mock": True,
            "source_type": MOCK_SOURCE_TYPE_LABEL,
        })

        # 2. Udyam
        udyam_records.append({
            "verification_id": f"MOCK-UDYAM-{e_id}",
            "source": "UDYAM",
            "entity_identifier": e_id,
            "status": b["udyam_status"],
            "udyam_registration_number": b["udyam"],
            "enterprise_name": b["company_name"],
            "enterprise_type": b["udyam_type"],
            "registration_date": "2020-08-15",
            "state": state_name,
            "district": f"{state_name} Central",
            "major_activity": "SERVICES",
            "verified_fields": {
                "udyam_number": b["udyam"],
                "category": b["udyam_type"],
                "valid": b["udyam_status"] == "ACTIVE",
            },
            "verification_timestamp": BASE_TIMESTAMP,
            "raw_response": {
                "source": "UDYAM_REGISTRY_SIMULATOR",
                "msme_category": b["udyam_type"],
                "registration_status": b["udyam_status"],
            },
            "is_mock": True,
            "source_type": MOCK_SOURCE_TYPE_LABEL,
        })

        # 3. MCA
        mca_records.append({
            "verification_id": f"MOCK-MCA-{e_id}",
            "source": "MCA",
            "entity_identifier": e_id,
            "status": b["mca_status"],
            "cin": b["cin"],
            "legal_name": b["mca_name"],
            "company_status": b["mca_status"],
            "incorporation_date": "2016-05-20",
            "registered_state": state_name,
            "company_type": "Private Limited Company" if "PTC" in b["cin"] else "Public Limited Company",
            "authorized_capital_cr": round(b["gstn_turnover"] * 0.4, 2),
            "verified_fields": {
                "cin": b["cin"],
                "legal_name": b["mca_name"],
                "status": b["mca_status"],
            },
            "verification_timestamp": BASE_TIMESTAMP,
            "raw_response": {
                "source": "MCA_REGISTRY_SIMULATOR",
                "company_name": b["mca_name"],
                "roc_status": b["mca_status"],
            },
            "is_mock": True,
            "source_type": MOCK_SOURCE_TYPE_LABEL,
        })

        # 4. Income Tax / PAN
        it_records.append({
            "verification_id": f"MOCK-IT-{e_id}",
            "source": "INCOME_TAX",
            "entity_identifier": e_id,
            "status": b["it_status"],
            "pan": b["pan"],
            "entity_name": b["company_name"],
            "pan_status": b["it_status"],
            "taxpayer_type": "COMPANY",
            "last_itr_filed_fy": "2024-25",
            "tax_compliance_status": "COMPLIANT" if b["it_status"] == "ACTIVE" else "NON_COMPLIANT",
            "verified_fields": {
                "pan": b["pan"],
                "pan_status": b["it_status"],
            },
            "verification_timestamp": BASE_TIMESTAMP,
            "raw_response": {
                "source": "INCOME_TAX_PAN_SIMULATOR",
                "pan": b["pan"],
                "is_active": b["it_status"] == "ACTIVE",
            },
            "is_mock": True,
            "source_type": MOCK_SOURCE_TYPE_LABEL,
        })

        # 5. MII
        mii_records.append({
            "verification_id": f"MOCK-MII-{e_id}",
            "source": "MII",
            "entity_identifier": e_id,
            "status": b["mii_status"],
            "product_category": "Server Compute Infrastructure & Workstations",
            "verified_local_content": b["mii_content"],
            "verification_status": b["mii_status"],
            "certifying_authority": "Statutory Auditor / Authorized CA",
            "certificate_reference": f"CA/MII/2026/{e_id}",
            "verified_fields": {
                "local_content_percentage": b["mii_content"],
                "class_status": b["mii_status"],
            },
            "verification_timestamp": BASE_TIMESTAMP,
            "raw_response": {
                "source": "MII_LOCAL_CONTENT_REGISTRY_SIMULATOR",
                "content_percentage": b["mii_content"],
                "verified_status": b["mii_status"],
            },
            "is_mock": True,
            "source_type": MOCK_SOURCE_TYPE_LABEL,
        })

    # -----------------------------------------------------------------------
    # Step 2: Generate remaining deterministic records up to 1,000 each
    # -----------------------------------------------------------------------
    base_date = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

    for i in range(11, 1001):
        e_id = f"SYNTH-BIDDER-{i:04d}"
        s_code, state_name, s_num = INDIAN_STATES[i % len(INDIAN_STATES)]
        c_prefix = ENTERPRISE_PREFIXES[(i * 7) % len(ENTERPRISE_PREFIXES)]
        c_core = ENTERPRISE_CORE[(i * 13) % len(ENTERPRISE_CORE)]
        suffix = "Pvt Ltd" if (i % 3 != 0) else "Ltd"
        comp_name = f"{c_prefix} {c_core} {suffix}"
        
        pan = _deterministic_pan(rng, i)
        gstin = _deterministic_gstin(rng, pan, s_num, i)
        cin = _deterministic_cin(rng, s_code, 2010 + (i % 14), i)
        udyam_num = f"UDYAM-{s_code}-{((i % 5) + 1):02d}-{1000000 + i}"
        
        # Determine status variations based on distribution
        # ~900 normal, ~30 turnover mismatch, ~20 inactive, ~15 name mismatch, ~15 unavailable, ~10 contradictions
        scenario_bucket = i % 100
        if scenario_bucket < 88:
            status_gstn = "ACTIVE"
            status_udyam = "ACTIVE"
            status_mca = "ACTIVE"
            status_it = "ACTIVE"
            status_mii = "VERIFIED_CLASS_I"
            turnover = round(rng.uniform(6.0, 80.0), 2)
            local_content = round(rng.uniform(50.0, 75.0), 1)
        elif scenario_bucket < 91:
            # Turnover mismatch / financial concern
            status_gstn = "ACTIVE"
            status_udyam = "ACTIVE"
            status_mca = "ACTIVE"
            status_it = "ACTIVE"
            status_mii = "VERIFIED_CLASS_I"
            turnover = round(rng.uniform(2.5, 4.9), 2)  # Shortfall
            local_content = round(rng.uniform(50.0, 65.0), 1)
        elif scenario_bucket < 93:
            # Inactive / Cancelled
            status_gstn = "CANCELLED"
            status_udyam = "CANCELLED"
            status_mca = "STRUCK_OFF"
            status_it = "INOPERATIVE"
            status_mii = "NON_LOCAL"
            turnover = round(rng.uniform(1.0, 5.0), 2)
            local_content = round(rng.uniform(15.0, 35.0), 1)
        elif scenario_bucket < 95:
            # Suspended / notice pending
            status_gstn = "SUSPENDED"
            status_udyam = "SUSPENDED"
            status_mca = "DORMANT"
            status_it = "INVALID"
            status_mii = "CONTRADICTION"
            turnover = round(rng.uniform(3.0, 10.0), 2)
            local_content = 32.0
        else:
            # Edge cases / Class II
            status_gstn = "ACTIVE"
            status_udyam = "ACTIVE"
            status_mca = "ACTIVE"
            status_it = "ACTIVE"
            status_mii = "VERIFIED_CLASS_II"
            turnover = round(rng.uniform(5.5, 30.0), 2)
            local_content = round(rng.uniform(40.0, 49.5), 1)

        udyam_type = "MICRO" if i % 4 == 0 else "SMALL" if i % 4 in (1, 2) else "MEDIUM"
        record_time = (base_date + timedelta(minutes=i * 3)).isoformat()

        # 1. GSTN
        gstn_records.append({
            "verification_id": f"MOCK-GSTN-{e_id}",
            "source": "GSTN",
            "entity_identifier": e_id,
            "status": status_gstn,
            "gstin": gstin,
            "legal_name": comp_name,
            "registration_status": status_gstn,
            "registration_date": f"201{7 + (i % 7):02d}-0{((i % 9) + 1):02d}-15",
            "state": state_name,
            "verified_turnover": turnover,
            "taxpayer_type": "Regular",
            "filing_status": "UP_TO_DATE" if status_gstn == "ACTIVE" else "DEFICIENT",
            "verified_fields": {
                "gstin": gstin,
                "annual_turnover_cr": turnover,
                "status": status_gstn,
            },
            "verification_timestamp": record_time,
            "raw_response": {
                "source": "GSTN_API_SIMULATOR",
                "retrieved_turnover": turnover,
                "is_active": status_gstn == "ACTIVE",
            },
            "is_mock": True,
            "source_type": MOCK_SOURCE_TYPE_LABEL,
        })

        # 2. Udyam
        udyam_records.append({
            "verification_id": f"MOCK-UDYAM-{e_id}",
            "source": "UDYAM",
            "entity_identifier": e_id,
            "status": status_udyam,
            "udyam_registration_number": udyam_num,
            "enterprise_name": comp_name,
            "enterprise_type": udyam_type,
            "registration_date": f"202{((i % 4)):02d}-0{((i % 9) + 1):02d}-10",
            "state": state_name,
            "district": f"{state_name} Region-{((i % 5) + 1)}",
            "major_activity": "SERVICES" if i % 2 == 0 else "MANUFACTURING",
            "verified_fields": {
                "udyam_number": udyam_num,
                "category": udyam_type,
                "valid": status_udyam == "ACTIVE",
            },
            "verification_timestamp": record_time,
            "raw_response": {
                "source": "UDYAM_REGISTRY_SIMULATOR",
                "msme_category": udyam_type,
                "registration_status": status_udyam,
            },
            "is_mock": True,
            "source_type": MOCK_SOURCE_TYPE_LABEL,
        })

        # 3. MCA
        mca_name = comp_name if scenario_bucket != 94 else comp_name.replace("Pvt Ltd", "Private Limited")
        mca_records.append({
            "verification_id": f"MOCK-MCA-{e_id}",
            "source": "MCA",
            "entity_identifier": e_id,
            "status": status_mca,
            "cin": cin,
            "legal_name": mca_name,
            "company_status": status_mca,
            "incorporation_date": f"201{4 + (i % 9):02d}-0{((i % 9) + 1):02d}-25",
            "registered_state": state_name,
            "company_type": "Private Limited Company" if "PTC" in cin else "Public Limited Company",
            "authorized_capital_cr": round(turnover * 0.35, 2),
            "verified_fields": {
                "cin": cin,
                "legal_name": mca_name,
                "status": status_mca,
            },
            "verification_timestamp": record_time,
            "raw_response": {
                "source": "MCA_REGISTRY_SIMULATOR",
                "company_name": mca_name,
                "roc_status": status_mca,
            },
            "is_mock": True,
            "source_type": MOCK_SOURCE_TYPE_LABEL,
        })

        # 4. Income Tax / PAN
        it_records.append({
            "verification_id": f"MOCK-IT-{e_id}",
            "source": "INCOME_TAX",
            "entity_identifier": e_id,
            "status": status_it,
            "pan": pan,
            "entity_name": comp_name,
            "pan_status": status_it,
            "taxpayer_type": "COMPANY",
            "last_itr_filed_fy": "2024-25" if status_it == "ACTIVE" else "2022-23",
            "tax_compliance_status": "COMPLIANT" if status_it == "ACTIVE" else "DEFICIENT",
            "verified_fields": {
                "pan": pan,
                "pan_status": status_it,
            },
            "verification_timestamp": record_time,
            "raw_response": {
                "source": "INCOME_TAX_PAN_SIMULATOR",
                "pan": pan,
                "is_active": status_it == "ACTIVE",
            },
            "is_mock": True,
            "source_type": MOCK_SOURCE_TYPE_LABEL,
        })

        # 5. MII
        mii_records.append({
            "verification_id": f"MOCK-MII-{e_id}",
            "source": "MII",
            "entity_identifier": e_id,
            "status": status_mii,
            "product_category": "Server Compute Infrastructure & Enterprise Nodes",
            "verified_local_content": local_content,
            "verification_status": status_mii,
            "certifying_authority": "Statutory Auditor / Authorized CA",
            "certificate_reference": f"CA/MII/2026/{e_id}",
            "verified_fields": {
                "local_content_percentage": local_content,
                "class_status": status_mii,
            },
            "verification_timestamp": record_time,
            "raw_response": {
                "source": "MII_LOCAL_CONTENT_REGISTRY_SIMULATOR",
                "content_percentage": local_content,
                "verified_status": status_mii,
            },
            "is_mock": True,
            "source_type": MOCK_SOURCE_TYPE_LABEL,
        })

    return gstn_records, udyam_records, mca_records, it_records, mii_records


def write_fixtures_to_disk(target_dir: str) -> Dict[str, int]:
    """Generate and write all 5 JSON fixture files deterministically."""
    os.makedirs(target_dir, exist_ok=True)
    gstn, udyam, mca, it, mii = generate_mock_datasets()

    files_map = {
        "gstn.json": gstn,
        "udyam.json": udyam,
        "mca.json": mca,
        "income_tax.json": it,
        "mii.json": mii,
    }

    counts = {}
    for filename, dataset in files_map.items():
        filepath = os.path.join(target_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(dataset, f, indent=2, ensure_ascii=False)
        counts[filename] = len(dataset)

    return counts


if __name__ == "__main__":
    import sys
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "../../mock_data")
    res = write_fixtures_to_disk(out_dir)
    print("Mock Data Generation Complete:")
    for k, v in res.items():
        print(f"  {k}: {v} records")
    print(f"  TOTAL: {sum(res.values())} records")
