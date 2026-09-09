# SIH26100 — Phase 6: Mock Integrated Verification Foundation

## 1. Phase Objective

Phase 6 introduces the architectural and data foundation for **Multi-Source Cross-Verification** within the SIH26100 AI-Powered Integrated Bid Compliance Verification Platform for GeM Procurement.

In actual public procurement workflows, verifying bidder compliance strictly based on submitted proposal PDFs leaves significant risk vectors open:
- Self-declared turnover figures may be fabricated or inflated compared to GST filings.
- Micro and Small Enterprise (MSE) exemption claims may lack valid Udyam statutory backing.
- Make in India (MII) local content declarations may conflict with audited supplier bills of materials.
- Vendors may bid under suspended, inactive, or cancelled legal corporate entities.

The objective of Phase 6.1 and 6.2 is to establish **authoritative source contracts**, **isolated database tables**, **deterministic synthetic registries (~5,000 records across 5 domains)**, and **idempotent database seeding** without touching or risking regression in the existing Day 1–5 compliance engine.

---

## 2. Current vs. Target Architecture

```
                               CURRENT BASELINE (Days 1–5)
                     ┌──────────────────────────────────────────┐
                     │   Tender PDF   ──► AI Clause Extractor   │
                     │   Bidder PDF   ──► Page-Aware Chunker    │
                     │   Retriever    ──► Hybrid Engine (PASS/  │
                     │                    FAIL/REVIEW/Conflict) │
                     └──────────────────────────────────────────┘
                                           │
                                           ▼ (Phase 6 Foundation)
                     ┌──────────────────────────────────────────┐
                     │     MOCK GOVERNMENT VERIFICATION LAYER   │
                     │                                          │
                     │  ┌───────────┐   ┌────────────────────┐ │
                     │  │JSON Stored│──►│ Idempotent Seeder  │ │
                     │  │ Fixtures  │   │(app/services/seeder│ │
                     │  └───────────┘   └─────────┬──────────┘ │
                     │                            │            │
                     │                            ▼            │
                     │  ┌───────────────────────────────────┐  │
                     │  │     Isolated Relational Tables    │  │
                     │  │  - mock_gstn_records              │  │
                     │  │  - mock_udyam_records             │  │
                     │  │  - mock_mca_records               │  │
                     │  │  - mock_income_tax_records        │  │
                     │  │  - mock_mii_records               │  │
                     │  └───────────────────────────────────┘  │
                     └──────────────────────────────────────────┘
                                           │
                                           ▼ (Future Phases 6.3 - 6.8)
                     ┌──────────────────────────────────────────┐
                     │  - Mock Source Providers (Phase 6.3)     │
                     │  - Verification Gateway  (Phase 6.4)     │
                     │  - Multi-Source Fusion   (Phase 6.5)     │
                     │  - Cross-Source Engine   (Phase 6.6)     │
                     │  - Scoring & Ranking     (Phase 6.7)     │
                     │  - Procurement UI Matrix (Phase 6.8)     │
                     └──────────────────────────────────────────┘
```

---

## 3. Mock Source Architecture & Data Boundary Rule

### Strict Data Boundary Isolation
A core architectural principle of Phase 6 is **strict source isolation**:
- **Bidder Proposal Domain**: Contains the bidder's self-declared claims (e.g., "Annual Turnover: ₹8.00 Crores" in the proposal document). These remain solely within the document extraction and chunking storage.
- **Authoritative Registry Domain**: Contains external registry verification responses (e.g., GSTN verified turnover: ₹3.65 Crores). These reside strictly in `mock_gstn_records`.
- Neither layer pollutes or overwrites the other. Cross-source contradiction detection (Phase 6.6) will evaluate both layers during evidence fusion.

### Mandatory Mock Labeling
Every synthetic record in every table contains:
- `is_mock = true` (Boolean)
- `source_type = "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"` (String)

This guarantees that synthetic records can never be misinterpreted or misrepresented as live government portal data.

---

## 4. Source Contracts (Pydantic Schemas)

Located in `backend/app/schemas/mock_sources.py`:

1. **`BaseMockVerificationSchema`**: Shared attributes across all sources:
   - `verification_id`: Unique deterministic audit ID (e.g., `MOCK-GSTN-BIDDER-01`).
   - `source`: Source identifier (`GSTN`, `UDYAM`, `MCA`, `INCOME_TAX`, `MII`).
   - `entity_identifier`: Bidder or enterprise identifier (e.g., `BIDDER-01`).
   - `status`: Verification status (`ACTIVE`, `VERIFIED`, `CANCELLED`, etc.).
   - `verified_fields`: Structured key-value dictionary of verified attributes.
   - `verification_timestamp`: ISO 8601 UTC timestamp.
   - `raw_response`: Simulated raw payload from registry API.
   - `is_mock`: Boolean (strictly `True`).
   - `source_type`: Fixed label `MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION`.

2. **`MockGSTNRecordSchema`**:
   - `gstin`: 15-character GST identification number.
   - `legal_name`: Registered legal entity name.
   - `registration_status`: `ACTIVE`, `CANCELLED`, `SUSPENDED`.
   - `registration_date`: YYYY-MM-DD.
   - `state`: State or UT.
   - `verified_turnover`: Annual turnover in INR Crores (Float).
   - `taxpayer_type`: `Regular`, `Composition`.
   - `filing_status`: `UP_TO_DATE`, `DEFICIENT`.

3. **`MockUdyamRecordSchema`**:
   - `udyam_registration_number`: Unique registration number (e.g., `UDYAM-MH-01-0026101`).
   - `enterprise_name`: Enterprise name.
   - `enterprise_type`: `MICRO`, `SMALL`, `MEDIUM`.
   - `status`: `ACTIVE`, `CANCELLED`, `SUSPENDED`.
   - `registration_date`, `state`, `district`, `major_activity`.

4. **`MockMCARecordSchema`**:
   - `cin`: 21-character Corporate Identity Number.
   - `legal_name`: Registered company name.
   - `company_status`: `ACTIVE`, `STRUCK_OFF`, `DORMANT`.
   - `incorporation_date`, `registered_state`, `company_type`, `authorized_capital_cr`.

5. **`MockIncomeTaxRecordSchema`**:
   - `pan`: 10-character Permanent Account Number.
   - `entity_name`: Name registered with PAN.
   - `pan_status`: `ACTIVE`, `INOPERATIVE`, `CANCELLED`, `INVALID`.
   - `taxpayer_type`, `last_itr_filed_fy`, `tax_compliance_status`.

6. **`MockMIIRecordSchema`**:
   - `product_category`: Hardware specification category.
   - `verified_local_content`: Local content percentage (0.0 to 100.0).
   - `verification_status`: `VERIFIED_CLASS_I`, `VERIFIED_CLASS_II`, `NON_LOCAL`, `CONTRADICTION`.
   - `certifying_authority`, `certificate_reference`.

---

## 5. Database Tables & Indexes

Located in `backend/app/models/mock_sources.py` (SQLAlchemy 2.0 ORM):

| Table Name | Primary Key | Critical Indexes |
| :--- | :--- | :--- |
| `mock_gstn_records` | `id` (UUID) | `verification_id` (unique), `gstin` (unique), `entity_identifier`, `status`, composite (`entity_identifier`, `status`) |
| `mock_udyam_records` | `id` (UUID) | `verification_id` (unique), `udyam_registration_number` (unique), `entity_identifier`, composite (`entity_identifier`, `enterprise_type`) |
| `mock_mca_records` | `id` (UUID) | `verification_id` (unique), `cin` (unique), `entity_identifier`, composite (`entity_identifier`, `company_status`) |
| `mock_income_tax_records` | `id` (UUID) | `verification_id` (unique), `pan` (unique), `entity_identifier`, composite (`entity_identifier`, `pan_status`) |
| `mock_mii_records` | `id` (UUID) | `verification_id` (unique), `entity_identifier`, composite (`entity_identifier`, `verified_local_content`) |

Runtime storage supports both PostgreSQL (with `pgvector`) and local SQLite (`gem_compliance.db`) via an automatic zero-configuration fallback mechanism.

---

## 6. JSON Fixtures & Generator

Located in `backend/mock_data/`:
- `gstn.json`: 1,000 records (860 KB)
- `udyam.json`: 1,000 records (877 KB)
- `mca.json`: 1,000 records (892 KB)
- `income_tax.json`: 1,000 records (751 KB)
- `mii.json`: 1,000 records (893 KB)
- **Total**: 5,000 records (4.27 MB)

**Generator**: `backend/app/services/mock_data_generator.py`
- Deterministic random seed: `26100` (no random drift across executions).
- Synthesizes realistic Indian corporate names, states, valid format GSTINs, CINs, PANs, and Udyam numbers without any real PII or secrets.

---

## 7. Idempotent Seeder

Located in `backend/app/services/mock_seeder.py`:
- Function: `seed_mock_sources(session: AsyncSession, fixtures_dir: Optional[Path] = None)`
- CLI: `python -m app.services.mock_seeder`
- **Idempotency Guarantee**: Checks existing `verification_id` set before insertion. Repeated invocations report `Inserted: 0`, ensuring zero duplication.

---

## 8. 10 Deterministic Showcase Bidders

Showcase bidders `BIDDER-01` through `BIDDER-10` have predetermined identities mapped across all 5 source registries:

| Bidder ID | Company / Entity Profile | GSTIN | Udyam Number | CIN | PAN | MII Verification ID |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **BIDDER-01** | Enterprise Tech Solutions Ltd (Benchmark Compliant) | `27AAACE1001A1Z1` | `UDYAM-MH-01-0026101` | `U72200MH2015PLC261001` | `AAACE1001A` | `MOCK-MII-BIDDER-01` |
| **BIDDER-02** | Apex System Integrators Pvt Ltd (Large Integrator) | `07BBBCB2002B1Z2` | `UDYAM-DL-02-0026102` | `U72200DL2016PTC261002` | `BBBCB2002B` | `MOCK-MII-BIDDER-02` |
| **BIDDER-03** | MicroEdge Networks LLP (MSE Exemption Showcase) | `29CCCCM3003C1Z3` | `UDYAM-KA-03-0026103` | `U72200KA2018PTC261003` | `CCCCM3003C` | `MOCK-MII-BIDDER-03` |
| **BIDDER-04** | Alpha Technologies Pvt Ltd (Name Variation Showcase)| `33DDDDN4004D1Z4` | `UDYAM-TN-04-0026104` | `U72200TN2017PTC261004` | `DDDDN4004D` | `MOCK-MII-BIDDER-04` |
| **BIDDER-05** | Horizon Cloud Infrastructure Pvt Ltd | `36EEEEH5005E1Z5` | `UDYAM-TS-05-0026105` | `U72200TG2019PTC261005` | `EEEEH5005E` | `MOCK-MII-BIDDER-05` |
| **BIDDER-06** | Nexus Data Communications Ltd | `24FFFFN6006F1Z6` | `UDYAM-GJ-06-0026106` | `U72200GJ2014PLC261006` | `FFFFN6006F` | `MOCK-MII-BIDDER-06` |
| **BIDDER-07** | Trident Global Enterprises | `19GGGGG7007G1Z7` | `UDYAM-WB-07-0026107` | `U72200WB2020PTC261007` | `GGGGG7007G` | `MOCK-MII-BIDDER-07` |
| **BIDDER-08** | Inactive Entity Showcase (Cancelled / Inoperative) | `06HHHHH8008H1Z8` | `UDYAM-HR-08-0026108` | `U72200HR2013PTC261008` | `HHHHH8008H` | `MOCK-MII-BIDDER-08` |
| **BIDDER-09** | Legacy Hardware Trading Co | `08IIIII9009I1Z9` | `UDYAM-RJ-09-0026109` | `U72200RJ2012PTC261009` | `IIIII9009I` | `MOCK-MII-BIDDER-09` |
| **BIDDER-10** | Contradictory Bidder Showcase (Turnover & MII Deficit) | `09JJJJJ0010J1Z0` | `UDYAM-UP-10-0026110` | `U72200UP2021PTC261010` | `JJJJJ0010J` | `MOCK-MII-BIDDER-10` |

---

## 9. Contradiction Fixture Scenarios

1. **Scenario 1 — Turnover Contradiction**:
   - *Bidder Document Claim*: Bidder declares ₹8.00 Cr annual turnover in tender bid document.
   - *Mock GSTN Record*: Record `MOCK-GSTN-BIDDER-10` specifies `verified_turnover = 3.65` (₹3.65 Cr).
   - *Future Fusion Outcome*: Detects a major statutory turnover shortfall against a ₹5.00 Cr requirement.

2. **Scenario 2 — MSE Exemption Verification**:
   - *Bidder Claim*: Claims EMD and tender fee waiver under MSE procurement policy.
   - *Mock Udyam Record*: Record `MOCK-UDYAM-BIDDER-03` confirms `status = "ACTIVE"` and `enterprise_type = "MICRO"`.
   - *Future Fusion Outcome*: Validates legitimate exemption privilege.

3. **Scenario 3 — Local Content (Make in India) Shortfall**:
   - *Bidder Claim*: Self-certifies 50% domestic content in cover letter.
   - *Bill of Materials (BOM) Evidence*: BOM extracts 32% local content.
   - *Mock MII Record*: Record `MOCK-MII-BIDDER-10` confirms `verified_local_content = 32.0`.
   - *Future Fusion Outcome*: Disqualifies Class-I preference and flags self-certification contradiction.

4. **Scenario 4 — Entity Legal Name Variation**:
   - *Bidder Document Submission*: "Alpha Technologies Pvt Ltd".
   - *Mock MCA Record*: Record `MOCK-MCA-BIDDER-04` legal name is "Alpha Technology Private Limited".
   - *Future Fusion Outcome*: Fuzzy identity matching confirms legal continuity without false rejection.

5. **Scenario 5 — Inactive / Suspended Statutory Status**:
   - *Bidder Submission*: Submits standard tender bid.
   - *Mock GSTN Record*: Record `MOCK-GSTN-BIDDER-08` has `status = "CANCELLED"`.
   - *Mock Income Tax Record*: Record `MOCK-IT-BIDDER-08` has `pan_status = "INOPERATIVE"`.
   - *Future Fusion Outcome*: Immediate disqualification recommendation.

---

## 10. Data Quality & Security Rules

- **Strictly Deterministic**: Reproducible seed `26100`.
- **Zero Real PII / Secrets**: All identifiers, company names, PANs, GSTINs, and CINs are synthetically generated.
- **Uniqueness Guarantees**:
  - `verification_id` is unique across all records within each domain.
  - Primary source keys (`gstin`, `udyam_registration_number`, `cin`, `pan`) are 100% unique within their respective tables.
- **Logical Isolation**: No foreign key constraints tie mock government sources to tender proposals, preventing cascade deletion and preserving audit trails.

---

## 11. UI Preview Implementation

Located in `frontend/src/app/tenders/[id]/bidders/page.tsx`:
- Adds an **"Integrated Verification Sources (Preview)"** card on the Bidder Workspace.
- Displays all 5 source cards (GSTN, Udyam, MCA, Income Tax, Make in India) with primary keys and record counts (~1,000 loaded).
- Each source clearly displays a `MOCK — SIH DEMONSTRATION` badge.
- Explicit disclaimer banner:
  > *"Architecture Notice: Government source connections shown here are synthetic demonstration data for SIH evaluation. Multi-source evidence fusion will be activated in subsequent verification phases."*
- Does NOT claim real connectivity or display fake live timestamps.

---

## 12. Current Status & Future Roadmap

| Milestone | Scope | Status |
| :--- | :--- | :--- |
| **Phase 6.1** | Source Contracts (Pydantic) + Database Models (SQLAlchemy) | **COMPLETED & VERIFIED** |
| **Phase 6.2** | Deterministic Synthetic Datasets (5,000 records) + Idempotent Seeder | **COMPLETED & VERIFIED** |
| **Phase 6.3** | Mock Source Providers & Gateway Adapters | *PLANNED (Awaiting Authorization)* |
| **Phase 6.4** | Runtime Verification Gateway & Request Routing | *PLANNED* |
| **Phase 6.5** | Multi-Source Evidence Fusion (Document + Registry) | *PLANNED* |
| **Phase 6.6** | Cross-Source Contradiction Engine Integration | *PLANNED* |
| **Phase 6.7** | Statutory Risk Scoring & Final Bidder Qualification Ranking | *PLANNED* |
| **Phase 6.8** | Procurement Officer Integrated Verification UI Dashboard | *PLANNED* |
