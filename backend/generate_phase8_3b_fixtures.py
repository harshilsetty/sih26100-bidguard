"""Generate deterministic synthetic datasets for Phase 8.3B:
1. NSIC Single Point Registration Scheme (1,000 records)
2. DigiLocker Document Verification/Provenance (1,000 records)

Total: 2,000 new mock records.
Seed: 26100.
Requirements:
- NSIC: SPRS registration details, issue_date, expiry_date, status, monetary limit.
- DigiLocker: document_reference, document_type, issuer, signature_status, verification_result, subject_pan, subject_cin.
- NO citizen secrets, NO employee PII, NO Aadhaar, NO real OAuth tokens.
- Explicitly labelled: is_mock = True, source_type = "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION".
- Deterministic showcase cases included.
"""

import json
import random
from pathlib import Path

SEED = 26100
TARGET_COUNT = 1000

PREFIXES = [
    "Astra", "Apex", "Zenith", "Vanguard", "Nexus", "Pinnacle", "Titan", "Quantum",
    "Synergy", "Meridian", "Vertex", "Paramount", "Horizon", "Sterling", "Summit", "Matrix",
    "Agile", "BluePeak", "CloudNine", "DataCraft", "EchoWave", "FutureLogic", "GreenTech", "HyperDrive"
]

MIDDLES = [
    "Innovations", "Dynamics", "Systems", "Technologies", "Solutions", "Infra",
    "Digital", "Logistics", "Engineering", "Robotics", "Analytics", "Networks"
]

SUFFIXES = [
    "Pvt Ltd", "Ltd", "LLP", "Enterprises", "Industries Ltd", "Services Pvt Ltd"
]

STATES = [
    "Maharashtra", "Delhi", "Karnataka", "Tamil Nadu", "Gujarat",
    "Telangana", "Uttar Pradesh", "Haryana", "West Bengal", "Rajasthan"
]

STATE_CODES = {
    "Maharashtra": ("MH", "27"),
    "Delhi": ("DL", "07"),
    "Karnataka": ("KA", "29"),
    "Tamil Nadu": ("TN", "33"),
    "Gujarat": ("GJ", "24"),
    "Telangana": ("TS", "36"),
    "Uttar Pradesh": ("UP", "09"),
    "Haryana": ("HR", "06"),
    "West Bengal": ("WB", "19"),
    "Rajasthan": ("RJ", "08"),
}

DOC_TYPES = [
    ("INCOME_TAX_PAN", "Income Tax Department", "ITD-DL-01"),
    ("GST_CERTIFICATE", "Goods and Services Tax Network", "GSTN-DL-01"),
    ("UDYAM_CERTIFICATE", "Ministry of Micro, Small & Medium Enterprises", "MSME-DL-01"),
    ("INCORPORATION_CERTIFICATE", "Ministry of Corporate Affairs", "MCA-DL-01"),
    ("COMPLIANCE_AUDIT_REPORT", "Quality Council of India", "QCI-DL-01"),
]


def _random_name(rng: random.Random) -> str:
    return f"{rng.choice(PREFIXES)} {rng.choice(MIDDLES)} {rng.choice(SUFFIXES)}"


def _generate_pan(rng: random.Random, idx: int) -> str:
    first3 = "AAA"
    forth = "C" if idx % 2 == 0 else "F"
    fifth = chr(ord('A') + (idx % 26))
    num = f"{(idx * 17 + 1000) % 9000 + 1000:04d}"
    last = chr(ord('A') + ((idx + 7) % 26))
    return f"{first3}{forth}{fifth}{num}{last}"


def _generate_cin(rng: random.Random, idx: int, state_code: str) -> str:
    listing = "U"
    code = f"{(idx * 13) % 90000 + 10000:05d}"
    year = 2015 + (idx % 10)
    ptc = "PTC" if idx % 2 == 0 else "PLC"
    reg = f"{(idx * 31 + 100000) % 900000 + 100000:06d}"
    return f"{listing}{code}{state_code}{year}{ptc}{reg}"


def generate_nsic_fixtures(output_path: Path):
    rng = random.Random(SEED)
    records = []

    # Showcase Records
    showcase = [
        # Case A: NSIC ACTIVE + valid
        {
            "verification_id": "MOCK-NSIC-DEMO-ACTIVE-001",
            "source": "NSIC",
            "entity_identifier": "DEMO-NSIC-ACTIVE-001",
            "registration_number": "NSIC-SPRS-11111",
            "entity_name": "Zenith Engineering Solutions Pvt Ltd",
            "pan": "AAACD1111A",
            "udyam_number": "UDYAM-MH-01-0011111",
            "registration_status": "ACTIVE",
            "status": "ACTIVE",
            "issue_date": "2023-01-01",
            "expiry_date": "2026-12-31",
            "monetary_limit": 50.0,
            "category": "SMALL",
            "store_details": "Mechanical & Electrical Equipment Manufacturing",
            "verified_fields": {
                "registration_number": "NSIC-SPRS-11111",
                "status": "ACTIVE",
                "monetary_limit_lakhs": 50.0,
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "NSIC_SPRS_SIMULATOR",
                "sprs_valid": True,
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Case B: NSIC EXPIRED
        {
            "verification_id": "MOCK-NSIC-DEMO-EXPIRED-001",
            "source": "NSIC",
            "entity_identifier": "DEMO-NSIC-EXPIRED-001",
            "registration_number": "NSIC-SPRS-22222",
            "entity_name": "Apex Precision Systems Ltd",
            "pan": "AAACD2222B",
            "udyam_number": "UDYAM-DL-02-0022222",
            "registration_status": "EXPIRED",
            "status": "EXPIRED",
            "issue_date": "2020-01-01",
            "expiry_date": "2022-12-31",
            "monetary_limit": 25.0,
            "category": "MICRO",
            "store_details": "Hardware Fabrication",
            "verified_fields": {
                "registration_number": "NSIC-SPRS-22222",
                "status": "EXPIRED",
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "NSIC_SPRS_SIMULATOR",
                "sprs_valid": False,
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Case D: NSIC INACTIVE
        {
            "verification_id": "MOCK-NSIC-DEMO-INACTIVE-001",
            "source": "NSIC",
            "entity_identifier": "DEMO-NSIC-INACTIVE-001",
            "registration_number": "NSIC-SPRS-33333",
            "entity_name": "Vanguard Infra Technologies Pvt Ltd",
            "pan": "AAACD3333C",
            "udyam_number": "UDYAM-KA-03-0033333",
            "registration_status": "INACTIVE",
            "status": "INACTIVE",
            "issue_date": "2023-05-01",
            "expiry_date": "2025-04-30",
            "monetary_limit": 10.0,
            "category": "MICRO",
            "store_details": "Civil Works",
            "verified_fields": {
                "registration_number": "NSIC-SPRS-33333",
                "status": "INACTIVE",
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "NSIC_SPRS_SIMULATOR",
                "sprs_valid": False,
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Case E: NSIC FUTURE / NOT-YET-VALID
        {
            "verification_id": "MOCK-NSIC-DEMO-FUTURE-001",
            "source": "NSIC",
            "entity_identifier": "DEMO-NSIC-FUTURE-001",
            "registration_number": "NSIC-SPRS-44444",
            "entity_name": "Quantum Robotics Enterprises",
            "pan": "AAACD4444D",
            "udyam_number": "UDYAM-TS-04-0044444",
            "registration_status": "ACTIVE",
            "status": "ACTIVE",
            "issue_date": "2027-01-01",
            "expiry_date": "2030-12-31",
            "monetary_limit": 100.0,
            "category": "MEDIUM",
            "store_details": "Advanced Automation Systems",
            "verified_fields": {
                "registration_number": "NSIC-SPRS-44444",
                "status": "ACTIVE",
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "NSIC_SPRS_SIMULATOR",
                "sprs_valid": True,
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Case F: NSIC Name-Only Ambiguous Showcase
        {
            "verification_id": "MOCK-NSIC-DEMO-AMBIGUOUS-001",
            "source": "NSIC",
            "entity_identifier": "DEMO-NSIC-AMBIGUOUS-001",
            "registration_number": "NSIC-SPRS-55555",
            "entity_name": "National Industries Pvt Ltd",
            "pan": "AAACD5555E",
            "udyam_number": "UDYAM-UP-05-0055555",
            "registration_status": "ACTIVE",
            "status": "ACTIVE",
            "issue_date": "2023-01-01",
            "expiry_date": "2026-12-31",
            "monetary_limit": 30.0,
            "category": "SMALL",
            "store_details": "General Supplies",
            "verified_fields": {
                "registration_number": "NSIC-SPRS-55555",
                "status": "ACTIVE",
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "NSIC_SPRS_SIMULATOR",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Case G: NSIC Source-Code/PAN Conflict Target (Belongs to PAN-G)
        {
            "verification_id": "MOCK-NSIC-DEMO-CONFLICT-001",
            "source": "NSIC",
            "entity_identifier": "DEMO-NSIC-CONFLICT-001",
            "registration_number": "NSIC-SPRS-66666",
            "entity_name": "Different Corp Logistics Pvt Ltd",
            "pan": "AAACD6666G",
            "udyam_number": "UDYAM-GJ-06-0066666",
            "registration_status": "ACTIVE",
            "status": "ACTIVE",
            "issue_date": "2023-01-01",
            "expiry_date": "2026-12-31",
            "monetary_limit": 40.0,
            "category": "SMALL",
            "store_details": "Logistics Services",
            "verified_fields": {
                "registration_number": "NSIC-SPRS-66666",
                "pan": "AAACD6666G",
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "NSIC_SPRS_SIMULATOR",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Case H: NSIC Consistent PAN + Registration Number
        {
            "verification_id": "MOCK-NSIC-DEMO-CONSISTENT-001",
            "source": "NSIC",
            "entity_identifier": "DEMO-NSIC-CONSISTENT-001",
            "registration_number": "NSIC-SPRS-77777",
            "entity_name": "Consistent Energy Solutions Ltd",
            "pan": "AAACD7777H",
            "udyam_number": "UDYAM-RJ-07-0077777",
            "registration_status": "ACTIVE",
            "status": "ACTIVE",
            "issue_date": "2022-01-01",
            "expiry_date": "2026-12-31",
            "monetary_limit": 75.0,
            "category": "MEDIUM",
            "store_details": "Renewable Energy Products",
            "verified_fields": {
                "registration_number": "NSIC-SPRS-77777",
                "pan": "AAACD7777H",
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "NSIC_SPRS_SIMULATOR",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Open-ended registration record (expiry_date: None, explicit PERMANENT)
        {
            "verification_id": "MOCK-NSIC-DEMO-INDEFINITE-001",
            "source": "NSIC",
            "entity_identifier": "DEMO-NSIC-INDEFINITE-001",
            "registration_number": "NSIC-SPRS-88888",
            "entity_name": "Permanent Industrial Trust",
            "pan": "AAACD8888P",
            "udyam_number": "UDYAM-TN-08-0088888",
            "registration_status": "PERMANENT",
            "status": "ACTIVE",
            "issue_date": "2018-01-01",
            "expiry_date": None,
            "monetary_limit": 200.0,
            "category": "MEDIUM",
            "store_details": "Heavy Industrial Castings",
            "verified_fields": {
                "registration_number": "NSIC-SPRS-88888",
                "status": "PERMANENT",
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "NSIC_SPRS_SIMULATOR",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Unspecified open-ended record (expiry_date: None, NOT declared permanent)
        {
            "verification_id": "MOCK-NSIC-DEMO-UNSPECIFIED-001",
            "source": "NSIC",
            "entity_identifier": "DEMO-NSIC-UNSPECIFIED-001",
            "registration_number": "NSIC-SPRS-99999",
            "entity_name": "Unspecified Term Enterprises",
            "pan": "AAACD9999U",
            "udyam_number": "UDYAM-HR-09-0099999",
            "registration_status": "ACTIVE",
            "status": "ACTIVE",
            "issue_date": "2023-01-01",
            "expiry_date": None,
            "monetary_limit": 15.0,
            "category": "MICRO",
            "store_details": "Standard Supplies",
            "verified_fields": {
                "registration_number": "NSIC-SPRS-99999",
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "NSIC_SPRS_SIMULATOR",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
    ]

    records.extend(showcase)
    start_idx = len(showcase) + 1

    for i in range(start_idx, TARGET_COUNT + 1):
        state = rng.choice(STATES)
        st_code, _ = STATE_CODES[state]
        reg_num = f"NSIC-SPRS-{i:05d}"
        ent_name = _random_name(rng)
        pan = _generate_pan(rng, i)
        udyam = f"UDYAM-{st_code}-{i % 30 + 1:02d}-{i * 11 % 9000000 + 1000000:07d}"

        # 85% Active, 10% Expired, 5% Inactive
        dice = rng.random()
        if dice < 0.85:
            reg_status = "ACTIVE"
            status = "ACTIVE"
            issue_year = rng.randint(2021, 2024)
            exp_year = issue_year + rng.choice([2, 3, 5])
        elif dice < 0.95:
            reg_status = "EXPIRED"
            status = "EXPIRED"
            issue_year = rng.randint(2018, 2020)
            exp_year = issue_year + 2
        else:
            reg_status = "INACTIVE"
            status = "INACTIVE"
            issue_year = rng.randint(2020, 2023)
            exp_year = issue_year + 3

        iss_month = rng.randint(1, 12)
        iss_day = rng.randint(1, 28)
        issue_date = f"{issue_year:04d}-{iss_month:02d}-{iss_day:02d}"
        expiry_date = f"{exp_year:04d}-{iss_month:02d}-{iss_day:02d}"
        limit = round(rng.uniform(5.0, 150.0), 2)
        category = rng.choice(["MICRO", "SMALL", "MEDIUM"])

        records.append({
            "verification_id": f"MOCK-NSIC-{i:04d}",
            "source": "NSIC",
            "entity_identifier": f"BIDDER-NSIC-{i:04d}",
            "registration_number": reg_num,
            "entity_name": ent_name,
            "pan": pan,
            "udyam_number": udyam,
            "registration_status": reg_status,
            "status": status,
            "issue_date": issue_date,
            "expiry_date": expiry_date,
            "monetary_limit": limit,
            "category": category,
            "store_details": f"Stores classification: Group {i % 10 + 1}",
            "verified_fields": {
                "registration_number": reg_num,
                "status": status,
                "monetary_limit_lakhs": limit,
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "NSIC_SPRS_SIMULATOR",
                "sprs_valid": (status == "ACTIVE"),
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    print(f"Generated {len(records)} NSIC records -> {output_path}")


def generate_digilocker_fixtures(output_path: Path):
    rng = random.Random(SEED)
    records = []

    # Showcase Records
    showcase = [
        # Case 1: Verified Document
        {
            "verification_id": "MOCK-DL-DEMO-VERIFIED-001",
            "source": "DIGILOCKER",
            "entity_identifier": "DEMO-DL-VERIFIED-001",
            "document_reference": "in.gov.pan-VER-001",
            "document_type": "INCOME_TAX_PAN",
            "issuer": "Income Tax Department",
            "issuer_identifier": "ITD-DL-01",
            "subject_entity_name": "Zenith Engineering Solutions Pvt Ltd",
            "subject_pan": "AAACD1111A",
            "subject_cin": "U72200MH2020PTC341111",
            "issued_at": "2023-01-15",
            "document_status": "ACTIVE",
            "signature_status": "VALID",
            "verification_result": "VERIFIED",
            "verified_fields": {
                "document_reference": "in.gov.pan-VER-001",
                "signature_valid": True,
                "issuer_verified": True,
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "DIGILOCKER_SIMULATOR",
                "cert_issuer": "CCA_INDIA_ROOT",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Case 2: Invalid Signature
        {
            "verification_id": "MOCK-DL-DEMO-SIG-INVALID-001",
            "source": "DIGILOCKER",
            "entity_identifier": "DEMO-DL-SIG-INVALID-001",
            "document_reference": "in.gov.mca-SIG-INVALID-001",
            "document_type": "INCORPORATION_CERTIFICATE",
            "issuer": "Ministry of Corporate Affairs",
            "issuer_identifier": "MCA-DL-01",
            "subject_entity_name": "Tampered Incorporation Entity Ltd",
            "subject_pan": "AAACD2222B",
            "subject_cin": "U72200DL2019PLC342222",
            "issued_at": "2021-06-10",
            "document_status": "ACTIVE",
            "signature_status": "INVALID",
            "verification_result": "FAILED",
            "verified_fields": {
                "document_reference": "in.gov.mca-SIG-INVALID-001",
                "signature_valid": False,
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "DIGILOCKER_SIMULATOR",
                "error": "SIGNATURE_HASH_MISMATCH",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Case 3: Revoked Document
        {
            "verification_id": "MOCK-DL-DEMO-REVOKED-001",
            "source": "DIGILOCKER",
            "entity_identifier": "DEMO-DL-REVOKED-001",
            "document_reference": "in.gov.gst-REVOKED-001",
            "document_type": "GST_CERTIFICATE",
            "issuer": "Goods and Services Tax Network",
            "issuer_identifier": "GSTN-DL-01",
            "subject_entity_name": "Revoked Supplier Enterprises",
            "subject_pan": "AAACD3333C",
            "subject_cin": None,
            "issued_at": "2022-03-20",
            "document_status": "REVOKED",
            "signature_status": "VALID",
            "verification_result": "UNVERIFIED",
            "verified_fields": {
                "document_reference": "in.gov.gst-REVOKED-001",
                "document_status": "REVOKED",
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "DIGILOCKER_SIMULATOR",
                "revocation_reason": "TAXPAYER_CANCELLED",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Case 4: Expired Document
        {
            "verification_id": "MOCK-DL-DEMO-EXPIRED-001",
            "source": "DIGILOCKER",
            "entity_identifier": "DEMO-DL-EXPIRED-001",
            "document_reference": "in.gov.udyam-EXPIRED-001",
            "document_type": "UDYAM_CERTIFICATE",
            "issuer": "Ministry of Micro, Small & Medium Enterprises",
            "issuer_identifier": "MSME-DL-01",
            "subject_entity_name": "Old MSME Enterprises",
            "subject_pan": "AAACD4444D",
            "subject_cin": None,
            "issued_at": "2019-01-01",
            "document_status": "EXPIRED",
            "signature_status": "VALID",
            "verification_result": "UNVERIFIED",
            "verified_fields": {
                "document_reference": "in.gov.udyam-EXPIRED-001",
                "document_status": "EXPIRED",
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "DIGILOCKER_SIMULATOR",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Case 5: Unverified Signature (Pending Independent Audit)
        {
            "verification_id": "MOCK-DL-DEMO-SIG-UNVERIFIED-001",
            "source": "DIGILOCKER",
            "entity_identifier": "DEMO-DL-SIG-UNVERIFIED-001",
            "document_reference": "in.gov.cert-UNVERIFIED-001",
            "document_type": "COMPLIANCE_AUDIT_REPORT",
            "issuer": "Quality Council of India",
            "issuer_identifier": "QCI-DL-01",
            "subject_entity_name": "Pending Verification Labs Ltd",
            "subject_pan": "AAACD5555E",
            "subject_cin": "U72200KA2021PTC345555",
            "issued_at": "2023-11-01",
            "document_status": "ACTIVE",
            "signature_status": "NOT_VERIFIED",
            "verification_result": "UNVERIFIED",
            "verified_fields": {
                "document_reference": "in.gov.cert-UNVERIFIED-001",
                "signature_status": "NOT_VERIFIED",
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "DIGILOCKER_SIMULATOR",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Case 6: Conflict Target (Subject PAN belongs to AAACD6666G)
        {
            "verification_id": "MOCK-DL-DEMO-CONFLICT-001",
            "source": "DIGILOCKER",
            "entity_identifier": "DEMO-DL-CONFLICT-001",
            "document_reference": "in.gov.pan-CONFLICT-001",
            "document_type": "INCOME_TAX_PAN",
            "issuer": "Income Tax Department",
            "issuer_identifier": "ITD-DL-01",
            "subject_entity_name": "Third Party Corporation Ltd",
            "subject_pan": "AAACD6666G",
            "subject_cin": "U72200GJ2020PLC346666",
            "issued_at": "2022-05-15",
            "document_status": "ACTIVE",
            "signature_status": "VALID",
            "verification_result": "VERIFIED",
            "verified_fields": {
                "document_reference": "in.gov.pan-CONFLICT-001",
                "subject_pan": "AAACD6666G",
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "DIGILOCKER_SIMULATOR",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
    ]

    records.extend(showcase)
    start_idx = len(showcase) + 1

    for i in range(start_idx, TARGET_COUNT + 1):
        state = rng.choice(STATES)
        st_code, _ = STATE_CODES[state]
        doc_type, issuer_name, issuer_code = rng.choice(DOC_TYPES)
        doc_ref = f"in.gov.{doc_type.lower()[:8]}-{i:06d}"
        ent_name = _random_name(rng)
        pan = _generate_pan(rng, i)
        cin = _generate_cin(rng, i, st_code)

        # 90% Valid Verified Active, 5% Invalid Signature, 3% Expired, 2% Revoked
        dice = rng.random()
        if dice < 0.90:
            doc_status = "ACTIVE"
            sig_status = "VALID"
            ver_result = "VERIFIED"
        elif dice < 0.95:
            doc_status = "ACTIVE"
            sig_status = "INVALID"
            ver_result = "FAILED"
        elif dice < 0.98:
            doc_status = "EXPIRED"
            sig_status = "VALID"
            ver_result = "UNVERIFIED"
        else:
            doc_status = "REVOKED"
            sig_status = "VALID"
            ver_result = "UNVERIFIED"

        issued_year = rng.randint(2021, 2024)
        issued_month = rng.randint(1, 12)
        issued_day = rng.randint(1, 28)
        issued_at = f"{issued_year:04d}-{issued_month:02d}-{issued_day:02d}"

        records.append({
            "verification_id": f"MOCK-DL-{i:04d}",
            "source": "DIGILOCKER",
            "entity_identifier": f"BIDDER-DL-{i:04d}",
            "document_reference": doc_ref,
            "document_type": doc_type,
            "issuer": issuer_name,
            "issuer_identifier": issuer_code,
            "subject_entity_name": ent_name,
            "subject_pan": pan,
            "subject_cin": cin,
            "issued_at": issued_at,
            "document_status": doc_status,
            "signature_status": sig_status,
            "verification_result": ver_result,
            "verified_fields": {
                "document_reference": doc_ref,
                "document_type": doc_type,
                "signature_valid": (sig_status == "VALID"),
                "verification_result": ver_result,
            },
            "verification_timestamp": "2024-01-15T10:00:00Z",
            "raw_response": {
                "source": "DIGILOCKER_SIMULATOR",
                "issuer": issuer_code,
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    print(f"Generated {len(records)} DigiLocker records -> {output_path}")


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent / "mock_data"
    base_dir.mkdir(parents=True, exist_ok=True)
    generate_nsic_fixtures(base_dir / "nsic.json")
    generate_digilocker_fixtures(base_dir / "digilocker.json")
