import pymupdf
from typing import Dict, Any

PAGE_RECT = pymupdf.Rect(40, 50, 550, 780)


def generate_bidder_a_pdf() -> bytes:
    """Generate synthetic 4-page procurement document for Bidder A (Clearly Compliant)."""
    doc = pymupdf.open()

    # Page 1: Technical proposal
    p1 = doc.new_page()
    p1.insert_textbox(
        PAGE_RECT,
        "SYNTHETIC PROCUREMENT BID SUBMISSION - STRICTLY FOR TESTING\n"
        "Tender Reference: GEM/2026/B/8912450\n"
        "Bidder Name: Enterprise Tech Solutions Ltd (Bidder A)\n\n"
        "SECTION 1: TECHNICAL ARCHITECTURE & INFRASTRUCTURE SPECIFICATIONS\n\n"
        "1.1 Compute Infrastructure:\n"
        "Bidder A confirms supply of enterprise rack servers equipped with minimum 64-core processors "
        "and 256GB ECC DDR5 RAM. All server nodes feature dual redundant power supplies and hardware RAID.\n\n"
        "1.2 Quality Standards & Certifications:\n"
        "All hardware components are fully certified under BIS and strictly comply with ISO 9001:2015 quality standards. "
        "Official certificates from certified registrars are appended.",
        fontsize=11
    )

    # Page 2: Financial qualification
    p2 = doc.new_page()
    p2.insert_textbox(
        PAGE_RECT,
        "SYNTHETIC PROCUREMENT BID SUBMISSION - STRICTLY FOR TESTING\n"
        "Tender Reference: GEM/2026/B/8912450\n"
        "Bidder Name: Enterprise Tech Solutions Ltd (Bidder A)\n\n"
        "SECTION 2: FINANCIAL QUALIFICATION & EARNEST MONEY DEPOSIT\n\n"
        "2.1 Annual Turnover:\n"
        "Average annual turnover of Bidder A during the last three financial years (FY 2022-23, FY 2023-24, FY 2024-25) "
        "is INR 6.85 Crores, exceeding the required threshold of INR 5.0 Crores. Audited balance sheets with CA UDIN are submitted.\n\n"
        "2.2 Earnest Money Deposit (EMD):\n"
        "Bidder A has submitted an Earnest Money Deposit of INR 10,00,000 via online bank guarantee through State Bank of India.",
        fontsize=11
    )

    # Page 3: Statutory & experience
    p3 = doc.new_page()
    p3.insert_textbox(
        PAGE_RECT,
        "SYNTHETIC PROCUREMENT BID SUBMISSION - STRICTLY FOR TESTING\n"
        "Tender Reference: GEM/2026/B/8912450\n"
        "Bidder Name: Enterprise Tech Solutions Ltd (Bidder A)\n\n"
        "SECTION 3: STATUTORY ELIGIBILITY & PAST EXPERIENCE\n\n"
        "3.1 Make in India (MII) Local Content:\n"
        "Class-I Local Supplier self-certification: Local content in offered servers is 62 percent, "
        "exceeding the mandatory 50 percent requirement.\n\n"
        "3.2 Contract Execution Track Record:\n"
        "Bidder A has successfully executed 3 similar enterprise IT infrastructure contracts for Central Government PSUs "
        "in the last 3 years, with total contract value exceeding INR 15 Crores.",
        fontsize=11
    )

    # Page 4: Warranty & delivery SLA
    p4 = doc.new_page()
    p4.insert_textbox(
        PAGE_RECT,
        "SYNTHETIC PROCUREMENT BID SUBMISSION - STRICTLY FOR TESTING\n"
        "Tender Reference: GEM/2026/B/8912450\n"
        "Bidder Name: Enterprise Tech Solutions Ltd (Bidder A)\n\n"
        "SECTION 4: WARRANTY & DELIVERY SCHEDULE\n\n"
        "4.1 Warranty Commitment:\n"
        "Comprehensive on-site OEM warranty of 3 years shall be provided for all supplied equipment, "
        "with 24x7 mission-critical replacement SLA.\n\n"
        "4.2 Delivery Timeline:\n"
        "All hardware items and software licenses must be delivered and installed within 30 days from contract award date.",
        fontsize=11
    )

    data = doc.write()
    doc.close()
    return data


def generate_bidder_b_pdf() -> bytes:
    """Generate synthetic 4-page procurement document for Bidder B (Clearly Non-Compliant)."""
    doc = pymupdf.open()

    # Page 1: Substandard hardware
    p1 = doc.new_page()
    p1.insert_textbox(
        PAGE_RECT,
        "SYNTHETIC PROCUREMENT BID SUBMISSION - STRICTLY FOR TESTING\n"
        "Tender Reference: GEM/2026/B/8912450\n"
        "Bidder Name: Legacy Hardware Trading Co (Bidder B)\n\n"
        "SECTION 1: TECHNICAL PROPOSAL\n\n"
        "1.1 Server Infrastructure:\n"
        "Bidder B proposes entry-level tower workstations equipped with 32-core processors and 128GB standard DDR4 RAM.\n\n"
        "1.2 Certification Status:\n"
        "BIS registration is currently pending application. ISO 9001 certification expired in November 2024 and renewal is under process.",
        fontsize=11
    )

    # Page 2: Financial shortfall
    p2 = doc.new_page()
    p2.insert_textbox(
        PAGE_RECT,
        "SYNTHETIC PROCUREMENT BID SUBMISSION - STRICTLY FOR TESTING\n"
        "Tender Reference: GEM/2026/B/8912450\n"
        "Bidder Name: Legacy Hardware Trading Co (Bidder B)\n\n"
        "SECTION 2: FINANCIAL TURNOVER & EMD\n\n"
        "2.1 Turnover Figures:\n"
        "The average annual turnover of Bidder B over the preceding three financial years is INR 2.1 Crores only.\n\n"
        "2.2 EMD Deposit:\n"
        "Bidder B has submitted an Earnest Money Deposit of INR 2,00,000 via NEFT challan.",
        fontsize=11
    )

    # Page 3: Inadequate local content & experience
    p3 = doc.new_page()
    p3.insert_textbox(
        PAGE_RECT,
        "SYNTHETIC PROCUREMENT BID SUBMISSION - STRICTLY FOR TESTING\n"
        "Tender Reference: GEM/2026/B/8912450\n"
        "Bidder Name: Legacy Hardware Trading Co (Bidder B)\n\n"
        "SECTION 3: LOCAL CONTENT & EXPERIENCE\n\n"
        "3.1 Make in India Category:\n"
        "Local content in the supplied equipment is estimated at 30 percent, qualifying under Class-II Local Supplier category.\n\n"
        "3.2 Contract History:\n"
        "Bidder B has executed only 1 enterprise IT contract in the last 4 years.",
        fontsize=11
    )

    # Page 4: Excessive delivery time & limited warranty
    p4 = doc.new_page()
    p4.insert_textbox(
        PAGE_RECT,
        "SYNTHETIC PROCUREMENT BID SUBMISSION - STRICTLY FOR TESTING\n"
        "Tender Reference: GEM/2026/B/8912450\n"
        "Bidder Name: Legacy Hardware Trading Co (Bidder B)\n\n"
        "SECTION 4: WARRANTY & SLA\n\n"
        "4.1 Warranty:\n"
        "Standard carry-in OEM warranty of 1 year shall be provided for the compute hardware.\n\n"
        "4.2 Delivery Timeline:\n"
        "Delivery and installation will require 90 days from contract award due to import shipment schedules.",
        fontsize=11
    )

    data = doc.write()
    doc.close()
    return data


def generate_bidder_c_pdf() -> bytes:
    """Generate synthetic 4-page procurement document for Bidder C (Contradictory / Suspicious)."""
    doc = pymupdf.open()

    # Page 1: Exaggerated MII declaration
    p1 = doc.new_page()
    p1.insert_textbox(
        PAGE_RECT,
        "SYNTHETIC PROCUREMENT BID SUBMISSION - STRICTLY FOR TESTING\n"
        "Tender Reference: GEM/2026/B/8912450\n"
        "Bidder Name: Apex System Integrators (Bidder C)\n\n"
        "SECTION 1: STATUTORY DECLARATION - MAKE IN INDIA\n\n"
        "1.1 Local Content Declaration:\n"
        "Bidder C solemnly declares that the local content in the offered compute servers is 55 percent, "
        "fully meeting Class-I Local Supplier criteria under Government of India guidelines.",
        fontsize=11
    )

    # Page 2: Contradictory Bill of Materials
    p2 = doc.new_page()
    p2.insert_textbox(
        PAGE_RECT,
        "SYNTHETIC PROCUREMENT BID SUBMISSION - STRICTLY FOR TESTING\n"
        "Tender Reference: GEM/2026/B/8912450\n"
        "Bidder Name: Apex System Integrators (Bidder C)\n\n"
        "SECTION 2: BILL OF MATERIALS BREAKDOWN\n\n"
        "2.1 Itemized Import Valuation:\n"
        "Imported motherboard sub-assemblies and processor units account for 68 percent of total bill of materials. "
        "Actual domestic value addition and local content stands at 32 percent at factory gate.",
        fontsize=11
    )

    # Page 3: Self-proclaimed turnover
    p3 = doc.new_page()
    p3.insert_textbox(
        PAGE_RECT,
        "SYNTHETIC PROCUREMENT BID SUBMISSION - STRICTLY FOR TESTING\n"
        "Tender Reference: GEM/2026/B/8912450\n"
        "Bidder Name: Apex System Integrators (Bidder C)\n\n"
        "SECTION 3: FINANCIAL DECLARATION LETTER\n\n"
        "3.1 Financial Capability:\n"
        "Management self-attestation claims annual business turnover exceeding INR 8.0 Crores across IT supply divisions.",
        fontsize=11
    )

    # Page 4: CA Audited balance sheet contradiction & partial warranty
    p4 = doc.new_page()
    p4.insert_textbox(
        PAGE_RECT,
        "SYNTHETIC PROCUREMENT BID SUBMISSION - STRICTLY FOR TESTING\n"
        "Tender Reference: GEM/2026/B/8912450\n"
        "Bidder Name: Apex System Integrators (Bidder C)\n\n"
        "SECTION 4: AUDITED CERTIFICATE & WARRANTY DETAILS\n\n"
        "4.1 Chartered Accountant Balance Sheet Summary:\n"
        "CA Certificate UDIN 24109823 confirms actual 3-year average turnover of the firm is INR 3.65 Crores only.\n\n"
        "4.2 Warranty:\n"
        "Base warranty of 1 year provided by OEM, with optional 2-year warranty extension subject to additional commercial payment.",
        fontsize=11
    )

    data = doc.write()
    doc.close()
    return data


def generate_empty_scanned_pdf() -> bytes:
    """Generate a synthetic 1-page blank PDF simulating an empty or text-less scanned document."""
    doc = pymupdf.open()
    doc.new_page()  # Blank page with no text
    data = doc.write()
    doc.close()
    return data
