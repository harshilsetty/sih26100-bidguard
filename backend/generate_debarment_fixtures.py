"""Generate deterministic synthetic debarment dataset for Phase 8.2.

Requirements:
- Exactly 1,000 records
- Deterministic seed: 26100
- Canonical showcase identifiers:
  DEMO-ACTIVE-001
  DEMO-EXPIRED-001
  DEMO-FUTURE-001
  DEMO-UNKNOWN-001
  DEMO-INDEFINITE-001
- DEMO-CLEAN-001 MUST NOT exist.
- All records visibly carry:
  is_mock = True
  source_type = "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"
"""

import json
import random
from pathlib import Path

SEED = 26100
TOTAL_RECORDS = 1000

AUTHORITIES = [
    "Central Public Procurement Portal",
    "Ministry of Railways",
    "Central Vigilance Commission",
    "National Highways Authority of India",
    "Department of Expenditure",
    "Ministry of Heavy Industries",
    "Department of Telecommunications",
    "Ministry of Defence",
    "CPWD - Central Public Works Department",
    "State Vigilance Commission",
]

REASONS = [
    "Corrupt and fraudulent practices in bidding",
    "Willful failure to execute contract obligations",
    "Submission of forged technical qualification certificates",
    "Collusive bidding and cartelization",
    "Severe non-compliance with statutory safety standards",
    "Default on security deposit and performance bank guarantee",
    "Material misrepresentation in bid parameters",
    "Breach of integrity pact clause 14.2",
]

COMPANY_NAMES_PREFIX = [
    "Zenith", "Apex", "Vanguard", "Nexus", "Pinnacle", "Titan", "Quantum", "Synergy",
    "Astra", "Meridian", "Vertex", "Paramount", "Horizon", "Sterling", "Summit", "Matrix"
]

COMPANY_NAMES_SUFFIX = [
    "Technologies Pvt Ltd", "Infra Projects Ltd", "Enterprises LLP", "Solutions Pvt Ltd",
    "Engineering Works Ltd", "Global Logistics Pvt Ltd", "Systems Corp", "Industries Ltd"
]

def generate_fixtures():
    random.seed(SEED)
    records = []

    # 1. Canonical Showcase Fixtures
    showcase = [
        {
            "verification_id": "MOCK-DEB-DEMO-ACTIVE-001",
            "source": "DEBARMENT",
            "entity_identifier": "DEMO-ACTIVE-001",
            "status": "ACTIVE",
            "pan": "AAACE1001A",
            "cin": "U72200MH2018PTC311001",
            "gstin": "27AAACE1001A1Z1",
            "udyam_registration_number": "UDYAM-MH-01-0011001",
            "firm_name": "Apex Global Dynamics Pvt Ltd",
            "order_number": "DEB/CPPP/2025/001",
            "authority_name": "Central Public Procurement Portal",
            "reason": "Corrupt and fraudulent practices in bidding",
            "start_date": "2025-01-01",
            "end_date": "2027-12-31",
            "verified_fields": {
                "pan": "AAACE1001A",
                "cin": "U72200MH2018PTC311001",
                "order_number": "DEB/CPPP/2025/001",
                "temporal_status": "ACTIVE_ON_DATE"
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "DEBARMENT_PORTAL_SIMULATOR",
                "order_status": "ENFORCED"
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"
        },
        {
            "verification_id": "MOCK-DEB-DEMO-EXPIRED-001",
            "source": "DEBARMENT",
            "entity_identifier": "DEMO-EXPIRED-001",
            "status": "EXPIRED",
            "pan": "AAACF2002B",
            "cin": "U72200DL2019PTC311002",
            "gstin": "07AAACF2002B1Z2",
            "udyam_registration_number": "UDYAM-DL-02-0022002",
            "firm_name": "Bharat Infratech Solutions",
            "order_number": "DEB/MHI/2022/042",
            "authority_name": "Ministry of Heavy Industries",
            "reason": "Failure to deliver project deliverables on time",
            "start_date": "2022-01-01",
            "end_date": "2024-12-31",
            "verified_fields": {
                "pan": "AAACF2002B",
                "cin": "U72200DL2019PTC311002",
                "order_number": "DEB/MHI/2022/042",
                "temporal_status": "EXPIRED_BEFORE_DATE"
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "DEBARMENT_PORTAL_SIMULATOR",
                "order_status": "PERIOD_CONCLUDED"
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"
        },
        {
            "verification_id": "MOCK-DEB-DEMO-FUTURE-001",
            "source": "DEBARMENT",
            "entity_identifier": "DEMO-FUTURE-001",
            "status": "ACTIVE",
            "pan": "AAACG3003C",
            "cin": "U72200KA2020PTC311003",
            "gstin": "29AAACG3003C1Z3",
            "udyam_registration_number": "UDYAM-KA-03-0033003",
            "firm_name": "Crest Engineering Works Ltd",
            "order_number": "DEB/DOT/2026/089",
            "authority_name": "Department of Telecommunications",
            "reason": "Prospective debarment effective next financial year",
            "start_date": "2027-01-01",
            "end_date": "2029-12-31",
            "verified_fields": {
                "pan": "AAACG3003C",
                "cin": "U72200KA2020PTC311003",
                "order_number": "DEB/DOT/2026/089",
                "temporal_status": "STARTS_AFTER_DATE"
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "DEBARMENT_PORTAL_SIMULATOR",
                "order_status": "SCHEDULED_FUTURE"
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"
        },
        {
            "verification_id": "MOCK-DEB-DEMO-UNKNOWN-001",
            "source": "DEBARMENT",
            "entity_identifier": "DEMO-UNKNOWN-001",
            "status": "UNDER_INQUIRY",
            "pan": "AAACH4004D",
            "cin": "U72200TN2021PTC311004",
            "gstin": "33AAACH4004D1Z4",
            "udyam_registration_number": "UDYAM-TN-04-0044004",
            "firm_name": "Delta System Integrators",
            "order_number": "DEB/SVC/2026/999",
            "authority_name": "State Vigilance Commission",
            "reason": "Administrative inquiry pending - dates unassigned",
            "start_date": None,
            "end_date": None,
            "verified_fields": {
                "pan": "AAACH4004D",
                "cin": "U72200TN2021PTC311004",
                "order_number": "DEB/SVC/2026/999",
                "temporal_status": "UNKNOWN_PERIOD"
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "DEBARMENT_PORTAL_SIMULATOR",
                "order_status": "DATES_UNAVAILABLE"
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"
        },
        {
            "verification_id": "MOCK-DEB-DEMO-INDEFINITE-001",
            "source": "DEBARMENT",
            "entity_identifier": "DEMO-INDEFINITE-001",
            "status": "ACTIVE_INDEFINITE",
            "pan": "AAACI5005E",
            "cin": "U72200GJ2022PTC311005",
            "gstin": "24AAACI5005E1Z5",
            "udyam_registration_number": "UDYAM-GJ-05-0055005",
            "firm_name": "Epsilon Cyber Logistics",
            "order_number": "DEB/MOD/2023/310",
            "authority_name": "Ministry of Defence",
            "reason": "Breach of national security protocol - indefinite debarment",
            "start_date": "2023-01-01",
            "end_date": None,
            "verified_fields": {
                "pan": "AAACI5005E",
                "cin": "U72200GJ2022PTC311005",
                "order_number": "DEB/MOD/2023/310",
                "temporal_status": "ACTIVE_ON_DATE"
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "DEBARMENT_PORTAL_SIMULATOR",
                "order_status": "PERMANENT_RECORD"
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"
        },
        {
            "verification_id": "MOCK-DEB-DEMO-PERMANENT-001",
            "source": "DEBARMENT",
            "entity_identifier": "DEMO-PERMANENT-001",
            "status": "PERMANENT",
            "pan": "AAACJ6006F",
            "cin": "U72200WB2021PTC311006",
            "gstin": "19AAACJ6006F1Z6",
            "udyam_registration_number": "UDYAM-WB-06-0066006",
            "firm_name": "Future Prime Technologies",
            "order_number": "DEB/CVC/2021/777",
            "authority_name": "Central Vigilance Commission",
            "reason": "Permanent disqualification due to grave fraud",
            "start_date": "2021-06-01",
            "end_date": None,
            "verified_fields": {
                "pan": "AAACJ6006F",
                "order_number": "DEB/CVC/2021/777",
                "temporal_status": "ACTIVE_ON_DATE"
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "DEBARMENT_PORTAL_SIMULATOR",
                "order_status": "PERMANENT"
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"
        },
        {
            "verification_id": "MOCK-DEB-DEMO-NULL-ORDINARY-001",
            "source": "DEBARMENT",
            "entity_identifier": "DEMO-NULL-ORDINARY-001",
            "status": "ACTIVE",
            "pan": "AAACK7007G",
            "cin": "U72200UP2022PTC311007",
            "gstin": "09AAACK7007G1Z7",
            "udyam_registration_number": "UDYAM-UP-07-0077007",
            "firm_name": "Galaxy Global Supplies",
            "order_number": "DEB/RAIL/2024/555",
            "authority_name": "Ministry of Railways",
            "reason": "Administrative suspension with null end date",
            "start_date": "2024-01-01",
            "end_date": None,
            "verified_fields": {
                "pan": "AAACK7007G",
                "order_number": "DEB/RAIL/2024/555",
                "temporal_status": "UNKNOWN_PERIOD"
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "DEBARMENT_PORTAL_SIMULATOR",
                "order_status": "ORDINARY_NULL_END"
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"
        },
        {
            "verification_id": "MOCK-DEB-DEMO-REVOKED-001",
            "source": "DEBARMENT",
            "entity_identifier": "DEMO-REVOKED-001",
            "status": "REVOKED",
            "pan": "AAACL8008H",
            "cin": "U72200RJ2023PTC311008",
            "gstin": "08AAACL8008H1Z8",
            "udyam_registration_number": "UDYAM-RJ-08-0088008",
            "firm_name": "Horizon Builders & Developers",
            "order_number": "DEB/PWD/2024/333",
            "authority_name": "CPWD - Central Public Works Department",
            "reason": "Debarment order quashed by Appellate Authority",
            "start_date": "2024-01-01",
            "end_date": "2027-12-31",
            "verified_fields": {
                "pan": "AAACL8008H",
                "order_number": "DEB/PWD/2024/333",
                "temporal_status": "EXPIRED_BEFORE_DATE"
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "DEBARMENT_PORTAL_SIMULATOR",
                "order_status": "REVOKED"
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"
        }
    ]

    records.extend(showcase)
    existing_count = len(records)
    remaining_needed = TOTAL_RECORDS - existing_count

    # Generate remaining records up to exactly 1,000
    for i in range(1, remaining_needed + 1):
        num_str = f"{i:04d}"
        ent_id = f"ENT-DEB-{num_str}"
        # Guarantee DEMO-CLEAN-001 does not exist
        if ent_id == "DEMO-CLEAN-001":
            ent_id = f"ENT-DEB-ALT-{num_str}"

        pan_letter = chr(65 + (i % 26))
        pan = f"AAAC{pan_letter}{num_str}"
        cin = f"U{10000 + (i % 90000)}MH20{15 + (i % 10)}PTC{100000 + i}"
        state_code = f"{(i % 35) + 1:02d}"
        gstin = f"{state_code}{pan}1Z{i % 9}"
        udyam = f"UDYAM-MH-{state_code}-{num_str}{i % 10}"

        prefix = random.choice(COMPANY_NAMES_PREFIX)
        suffix = random.choice(COMPANY_NAMES_SUFFIX)
        firm_name = f"{prefix} {suffix} #{num_str}"

        authority = random.choice(AUTHORITIES)
        reason = random.choice(REASONS)

        # Diverse temporal profiles
        profile_dice = random.random()
        if profile_dice < 0.35:
            # Active interval
            s_yr = 2024 + (i % 2)
            e_yr = 2026 + (i % 3) + 1
            s_date = f"{s_yr}-0{1 + (i % 8)}-01"
            e_date = f"{e_yr}-12-31"
            status = "ACTIVE"
        elif profile_dice < 0.65:
            # Expired interval
            s_yr = 2020 + (i % 3)
            e_yr = 2023 + (i % 2)
            s_date = f"{s_yr}-01-15"
            e_date = f"{e_yr}-06-30"
            status = "EXPIRED"
        elif profile_dice < 0.80:
            # Future interval
            s_yr = 2027 + (i % 2)
            e_yr = 2029 + (i % 2)
            s_date = f"{s_yr}-01-01"
            e_date = f"{e_yr}-12-31"
            status = "ACTIVE"
        elif profile_dice < 0.90:
            # Open-ended
            s_yr = 2022 + (i % 3)
            s_date = f"{s_yr}-01-01"
            e_date = None
            status = "ACTIVE_INDEFINITE" if (i % 2 == 0) else "PERMANENT"
        else:
            # Unknown / missing dates
            s_date = None
            e_date = None
            status = "UNDER_INQUIRY"

        rec = {
            "verification_id": f"MOCK-DEB-{num_str}",
            "source": "DEBARMENT",
            "entity_identifier": ent_id,
            "status": status,
            "pan": pan,
            "cin": cin,
            "gstin": gstin,
            "udyam_registration_number": udyam,
            "firm_name": firm_name,
            "order_number": f"DEB/MOCK/{2020 + (i % 7)}/{num_str}",
            "authority_name": authority,
            "reason": reason,
            "start_date": s_date,
            "end_date": e_date,
            "verified_fields": {
                "pan": pan,
                "cin": cin,
                "order_number": f"DEB/MOCK/{2020 + (i % 7)}/{num_str}"
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "DEBARMENT_PORTAL_SIMULATOR",
                "simulated_record_id": num_str
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"
        }
        records.append(rec)

    # Double check record count and DEMO-CLEAN-001 absence
    assert len(records) == TOTAL_RECORDS, f"Expected {TOTAL_RECORDS}, got {len(records)}"
    for r in records:
        assert r["entity_identifier"] != "DEMO-CLEAN-001"
        assert r["is_mock"] is True
        assert r["source_type"] == "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"

    out_path = Path(__file__).resolve().parent / "mock_data" / "debarment.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    print(f"Successfully generated exactly {len(records)} debarment records to {out_path}")

if __name__ == "__main__":
    generate_fixtures()
