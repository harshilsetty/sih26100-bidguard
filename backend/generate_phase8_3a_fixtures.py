"""Generate deterministic synthetic datasets for Phase 8.3A:
1. DPIIT / Startup India (1,000 records)
2. EPFO Establishment Registry (1,000 records)
3. ESIC Establishment/Employer Registry (1,000 records)

Total: 3,000 new mock records.
Seed: 26100.
Requirements:
- Establishment-level only for EPFO and ESIC (NO employee-level data).
- Explicitly labelled: is_mock = True, source_type = "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION".
- No credentials, tokens, or citizen secrets.
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


def _random_name(rng: random.Random) -> str:
    return f"{rng.choice(PREFIXES)} {rng.choice(MIDDLES)} {rng.choice(SUFFIXES)}"


def _generate_pan(rng: random.Random, idx: int) -> str:
    # 5 letters, 4 digits, 1 letter
    first3 = "AAA"
    forth = "C" if idx % 2 == 0 else "F"
    fifth = chr(ord('A') + (idx % 26))
    num = f"{(idx * 17 + 1000) % 9000 + 1000:04d}"
    last = chr(ord('A') + ((idx + 7) % 26))
    return f"{first3}{forth}{fifth}{num}{last}"


def _generate_cin(rng: random.Random, idx: int, state_code: str) -> str:
    # U/L + 5 digits + 2 state + 4 year + PTC/PLC + 6 digits
    listing = "U"
    code = f"{(idx * 13) % 90000 + 10000:05d}"
    year = 2015 + (idx % 10)
    ptc = "PTC" if idx % 2 == 0 else "PLC"
    reg = f"{(idx * 31 + 100000) % 900000 + 100000:06d}"
    return f"{listing}{code}{state_code}{year}{ptc}{reg}"


def generate_dpiit_fixtures(output_path: Path):
    rng = random.Random(SEED)
    records = []

    # Showcase Records
    showcase = [
        # Case A: Clean DPIIT Active
        {
            "verification_id": "MOCK-DPIIT-DEMO-ACTIVE-001",
            "source": "DPIIT",
            "entity_identifier": "DEMO-DPIIT-ACTIVE-001",
            "certificate_number": "DIPP11111",
            "entity_name": "Zenith Startup Innovations Pvt Ltd",
            "pan": "AAACD1111A",
            "cin": "U72200MH2020PTC341111",
            "status": "ACTIVE",
            "recognition_date": "2020-08-15",
            "valid_until": "2030-08-14",
            "industry_sector": "Technology",
            "verified_fields": {
                "certificate_number": "DIPP11111",
                "pan": "AAACD1111A",
                "cin": "U72200MH2020PTC341111",
                "status": "ACTIVE",
                "startup_india_recognized": True,
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "DPIIT_STARTUP_INDIA_SIMULATOR",
                "recognition_status": "RECOGNIZED",
                "tax_exemption_80IAC": True,
                "dpiit_number": "DIPP11111",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Case: DPIIT Inactive / Expired
        {
            "verification_id": "MOCK-DPIIT-DEMO-INACTIVE-001",
            "source": "DPIIT",
            "entity_identifier": "DEMO-DPIIT-INACTIVE-001",
            "certificate_number": "DIPP22222",
            "entity_name": "Vanguard Legacy Ventures Pvt Ltd",
            "pan": "AAACD2222B",
            "cin": "U72200DL2019PTC342222",
            "status": "INACTIVE",
            "recognition_date": "2015-05-10",
            "valid_until": "2025-05-09",
            "industry_sector": "Manufacturing",
            "verified_fields": {
                "certificate_number": "DIPP22222",
                "pan": "AAACD2222B",
                "cin": "U72200DL2019PTC342222",
                "status": "INACTIVE",
                "startup_india_recognized": False,
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "DPIIT_STARTUP_INDIA_SIMULATOR",
                "recognition_status": "EXPIRED_TEN_YEAR_LIMIT",
                "tax_exemption_80IAC": False,
                "dpiit_number": "DIPP22222",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Case C: DPIIT Ambiguous (Has name 'Startup India Innovations Pvt Ltd' with specific PAN/CIN)
        {
            "verification_id": "MOCK-DPIIT-DEMO-AMBIGUOUS-001",
            "source": "DPIIT",
            "entity_identifier": "DEMO-DPIIT-AMBIGUOUS-001",
            "certificate_number": "DIPP33333",
            "entity_name": "Startup India Innovations Pvt Ltd",
            "pan": "AAACD3333C",
            "cin": "U72200KA2021PTC343333",
            "status": "ACTIVE",
            "recognition_date": "2021-02-18",
            "valid_until": "2031-02-17",
            "industry_sector": "Artificial Intelligence",
            "verified_fields": {
                "certificate_number": "DIPP33333",
                "pan": "AAACD3333C",
                "cin": "U72200KA2021PTC343333",
                "status": "ACTIVE",
                "startup_india_recognized": True,
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "DPIIT_STARTUP_INDIA_SIMULATOR",
                "recognition_status": "RECOGNIZED",
                "tax_exemption_80IAC": True,
                "dpiit_number": "DIPP33333",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
    ]

    records.extend(showcase)

    # Fill remaining to exactly 1,000
    for i in range(len(showcase) + 1, TARGET_COUNT + 1):
        idx = i + 100
        state = rng.choice(STATES)
        state_code, _ = STATE_CODES[state]
        pan = _generate_pan(rng, idx)
        cin = _generate_cin(rng, idx, state_code)
        cert_num = f"DIPP{idx:05d}"
        entity_name = _random_name(rng)
        status = "ACTIVE" if rng.random() > 0.12 else "INACTIVE"
        year = 2018 + (idx % 7)
        rec_date = f"{year}-{(idx % 12) + 1:02d}-{(idx % 28) + 1:02d}"
        val_date = f"{year + 10}-{(idx % 12) + 1:02d}-{(idx % 28) + 1:02d}"

        records.append({
            "verification_id": f"MOCK-DPIIT-{i:04d}",
            "source": "DPIIT",
            "entity_identifier": f"BIDDER-DPIIT-{i:04d}",
            "certificate_number": cert_num,
            "entity_name": entity_name,
            "pan": pan,
            "cin": cin,
            "status": status,
            "recognition_date": rec_date,
            "valid_until": val_date,
            "industry_sector": "Software & Services",
            "verified_fields": {
                "certificate_number": cert_num,
                "pan": pan,
                "cin": cin,
                "status": status,
                "startup_india_recognized": (status == "ACTIVE"),
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "DPIIT_STARTUP_INDIA_SIMULATOR",
                "recognition_status": "RECOGNIZED" if status == "ACTIVE" else "DERECOGNIZED",
                "dpiit_number": cert_num,
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    print(f"Generated {len(records)} DPIIT records -> {output_path}")


def generate_epfo_fixtures(output_path: Path):
    rng = random.Random(SEED + 100)
    records = []

    # Showcase Records
    showcase = [
        # Case D: EPFO Active
        {
            "verification_id": "MOCK-EPFO-DEMO-ACTIVE-001",
            "source": "EPFO",
            "entity_identifier": "DEMO-EPFO-ACTIVE-001",
            "establishment_code": "MHBAN0010010000",
            "establishment_name": "Apex Engineering Works Ltd",
            "pan": "AAACE1001A",
            "status": "ACTIVE",
            "registration_date": "2018-04-01",
            "office_name": "Bandra, Mumbai",
            "exemption_status": "UNEXEMPTED",
            "verified_fields": {
                "establishment_code": "MHBAN0010010000",
                "establishment_name": "Apex Engineering Works Ltd",
                "pan": "AAACE1001A",
                "status": "ACTIVE",
                "coverage_status": "COVERED",
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "EPFO_UNIFIED_PORTAL_SIMULATOR",
                "establishment_status": "OPERATIONAL",
                "office_name": "Bandra, Mumbai",
                "exemption_status": "UNEXEMPTED",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Case E: EPFO Inactive
        {
            "verification_id": "MOCK-EPFO-DEMO-INACTIVE-001",
            "source": "EPFO",
            "entity_identifier": "DEMO-EPFO-INACTIVE-001",
            "establishment_code": "DLCPM0020020000",
            "establishment_name": "Matrix Logistics Inactive Pvt Ltd",
            "pan": "AAACE2002B",
            "status": "INACTIVE",
            "registration_date": "2016-01-15",
            "office_name": "Connaught Place, Delhi",
            "exemption_status": "UNEXEMPTED",
            "verified_fields": {
                "establishment_code": "DLCPM0020020000",
                "establishment_name": "Matrix Logistics Inactive Pvt Ltd",
                "pan": "AAACE2002B",
                "status": "INACTIVE",
                "coverage_status": "DORMANT_OR_CLOSED",
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "EPFO_UNIFIED_PORTAL_SIMULATOR",
                "establishment_status": "CLOSED",
                "office_name": "Connaught Place, Delhi",
                "closure_date": "2023-11-30",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
    ]

    records.extend(showcase)

    EPFO_OFFICES = [
        ("MH", "BAN", "Bandra"), ("MH", "PUN", "Pune"), ("DL", "CPM", "Delhi North"),
        ("KA", "BGN", "Bangalore"), ("TN", "MAS", "Chennai"), ("GJ", "AHD", "Ahmedabad"),
        ("TS", "HYD", "Hyderabad"), ("UP", "KAN", "Kanpur"), ("HR", "GGN", "Gurugram")
    ]

    # Fill remaining to exactly 1,000
    for i in range(len(showcase) + 1, TARGET_COUNT + 1):
        idx = i + 200
        state_code, office_code, office_name = rng.choice(EPFO_OFFICES)
        est_code = f"{state_code}{office_code}{idx:07d}000"
        est_name = _random_name(rng)
        pan = _generate_pan(rng, idx)
        status = "ACTIVE" if rng.random() > 0.10 else "INACTIVE"
        year = 2012 + (idx % 12)
        reg_date = f"{year}-{(idx % 12) + 1:02d}-{(idx % 28) + 1:02d}"

        records.append({
            "verification_id": f"MOCK-EPFO-{i:04d}",
            "source": "EPFO",
            "entity_identifier": f"BIDDER-EPFO-{i:04d}",
            "establishment_code": est_code,
            "establishment_name": est_name,
            "pan": pan,
            "status": status,
            "registration_date": reg_date,
            "office_name": office_name,
            "exemption_status": "UNEXEMPTED",
            "verified_fields": {
                "establishment_code": est_code,
                "establishment_name": est_name,
                "pan": pan,
                "status": status,
                "coverage_status": "COVERED" if status == "ACTIVE" else "INACTIVE",
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "EPFO_UNIFIED_PORTAL_SIMULATOR",
                "establishment_status": "OPERATIONAL" if status == "ACTIVE" else "CLOSED",
                "office_name": office_name,
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    print(f"Generated {len(records)} EPFO records -> {output_path}")


def generate_esic_fixtures(output_path: Path):
    rng = random.Random(SEED + 200)
    records = []

    # Showcase Records
    showcase = [
        # Case F: ESIC Active
        {
            "verification_id": "MOCK-ESIC-DEMO-ACTIVE-001",
            "source": "ESIC",
            "entity_identifier": "DEMO-ESIC-ACTIVE-001",
            "esic_code": "31000100100001001",
            "employer_name": "Apex Engineering Works Ltd",
            "pan": "AAACE1001A",
            "status": "ACTIVE",
            "registration_date": "2018-05-10",
            "region": "Maharashtra",
            "verified_fields": {
                "esic_code": "31000100100001001",
                "employer_name": "Apex Engineering Works Ltd",
                "pan": "AAACE1001A",
                "status": "ACTIVE",
                "region": "Maharashtra",
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "ESIC_PORTAL_SIMULATOR",
                "employer_status": "REGISTERED_ACTIVE",
                "regional_office": "RO Mumbai",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
        # Case: ESIC Inactive
        {
            "verification_id": "MOCK-ESIC-DEMO-INACTIVE-001",
            "source": "ESIC",
            "entity_identifier": "DEMO-ESIC-INACTIVE-001",
            "esic_code": "11000200200001002",
            "employer_name": "Matrix Logistics Inactive Pvt Ltd",
            "pan": "AAACE2002B",
            "status": "INACTIVE",
            "registration_date": "2016-02-20",
            "region": "Delhi",
            "verified_fields": {
                "esic_code": "11000200200001002",
                "employer_name": "Matrix Logistics Inactive Pvt Ltd",
                "pan": "AAACE2002B",
                "status": "INACTIVE",
                "region": "Delhi",
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "ESIC_PORTAL_SIMULATOR",
                "employer_status": "DEREGISTERED",
                "regional_office": "RO Delhi",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        },
    ]

    records.extend(showcase)

    # 17-digit code format: RR000XXXXX0001001
    STATE_PREFIX_MAP = {
        "Maharashtra": "31", "Delhi": "11", "Karnataka": "53", "Tamil Nadu": "51",
        "Gujarat": "37", "Telangana": "52", "Uttar Pradesh": "21", "Haryana": "13",
        "West Bengal": "41", "Rajasthan": "15"
    }

    # Fill remaining to exactly 1,000
    for i in range(len(showcase) + 1, TARGET_COUNT + 1):
        idx = i + 300
        state = rng.choice(STATES)
        prefix = STATE_PREFIX_MAP[state]
        esic_code = f"{prefix}000{idx:05d}0001001"
        employer_name = _random_name(rng)
        pan = _generate_pan(rng, idx)
        status = "ACTIVE" if rng.random() > 0.10 else "INACTIVE"
        year = 2013 + (idx % 11)
        reg_date = f"{year}-{(idx % 12) + 1:02d}-{(idx % 28) + 1:02d}"

        records.append({
            "verification_id": f"MOCK-ESIC-{i:04d}",
            "source": "ESIC",
            "entity_identifier": f"BIDDER-ESIC-{i:04d}",
            "esic_code": esic_code,
            "employer_name": employer_name,
            "pan": pan,
            "status": status,
            "registration_date": reg_date,
            "region": state,
            "verified_fields": {
                "esic_code": esic_code,
                "employer_name": employer_name,
                "pan": pan,
                "status": status,
                "region": state,
            },
            "verification_timestamp": "2026-03-01T10:00:00Z",
            "raw_response": {
                "source": "ESIC_PORTAL_SIMULATOR",
                "employer_status": "REGISTERED_ACTIVE" if status == "ACTIVE" else "SUSPENDED",
                "regional_office": f"RO {state}",
            },
            "is_mock": True,
            "source_type": "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION",
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    print(f"Generated {len(records)} ESIC records -> {output_path}")


def main():
    mock_dir = Path(__file__).resolve().parent / "mock_data"
    mock_dir.mkdir(parents=True, exist_ok=True)
    generate_dpiit_fixtures(mock_dir / "dpiit.json")
    generate_epfo_fixtures(mock_dir / "epfo.json")
    generate_esic_fixtures(mock_dir / "esic.json")
    print("Phase 8.3A fixture generation complete. Total 3,000 records.")


if __name__ == "__main__":
    main()
