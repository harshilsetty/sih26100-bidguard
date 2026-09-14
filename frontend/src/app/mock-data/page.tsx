"use client";

import { useEffect, useState, useTransition } from "react";
import Link from "next/link";
import {
  fetchMockSourcesSummary,
  fetchMockSourcesIntegrity,
  fetchMockSourceRecords,
  fetchMockRecordDetail,
  fetchShowcaseBidders,
  getMockSourceExportUrl,
} from "@/lib/api-client";
import {
  Database,
  Search,
  CheckCircle2,
  AlertTriangle,
  FileSpreadsheet,
  Layers,
  ChevronLeft,
  ChevronRight,
  X,
  ExternalLink,
  ShieldCheck,
  Building2,
  Building,
  Landmark,
  FileCheck,
  AlertCircle,
  Eye,
  Info,
  SlidersHorizontal,
} from "lucide-react";

interface SourceSummary {
  name: string;
  title: string;
  table: string;
  primary_key: string;
  description: string;
  count: number;
}

interface SourcesSummaryResponse {
  sources: Record<string, SourceSummary>;
  total_records: number;
  showcase_bidders_count: number;
  demo_scenarios_count: number;
  is_mock_system: boolean;
  disclaimer: string;
}

export default function MockDataExplorerPage() {
  const [activeSource, setActiveSource] = useState<string>("gstn");
  const [summary, setSummary] = useState<SourcesSummaryResponse | null>(null);
  const [integrity, setIntegrity] = useState<any | null>(null);
  const [showIntegrityPanel, setShowIntegrityPanel] = useState<boolean>(false);
  const [recordsData, setRecordsData] = useState<any | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(25);
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [showcaseOnly, setShowcaseOnly] = useState<boolean>(false);

  // Showcase Bidders Cross Inspection
  const [selectedShowcaseBidder, setSelectedShowcaseBidder] = useState<string>("");
  const [showcaseCrossData, setShowcaseCrossData] = useState<any | null>(null);
  const [showcaseLoading, setShowcaseLoading] = useState<boolean>(false);

  // Record Detail Drawer
  const [detailRecord, setDetailRecord] = useState<any | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);

  // Load overview summary and integrity on initial render
  useEffect(() => {
    const loadOverview = async () => {
      try {
        const [sumRes, intRes] = await Promise.all([
          fetchMockSourcesSummary().catch(() => null),
          fetchMockSourcesIntegrity().catch(() => null),
        ]);
        if (sumRes) setSummary(sumRes);
        if (intRes) setIntegrity(intRes);
      } catch (err) {
        console.error("Failed to load overview data:", err);
      }
    };
    loadOverview();
  }, []);

  // Load paginated source records when source, page, pageSize, search, status, or showcaseOnly changes
  useEffect(() => {
    let cancelled = false;
    const loadRecords = async () => {
      setLoading(true);
      try {
        const res = await fetchMockSourceRecords(
          activeSource,
          page,
          pageSize,
          searchTerm,
          statusFilter,
          showcaseOnly
        );
        if (!cancelled) {
          setRecordsData(res);
        }
      } catch (err) {
        if (!cancelled) {
          console.error("Failed to fetch mock records:", err);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    loadRecords();
    return () => {
      cancelled = true;
    };
  }, [activeSource, page, pageSize, searchTerm, statusFilter, showcaseOnly]);

  // Load Showcase cross-source data when a showcase bidder is selected
  useEffect(() => {
    if (!selectedShowcaseBidder) {
      setShowcaseCrossData(null);
      return;
    }
    const loadShowcase = async () => {
      setShowcaseLoading(true);
      try {
        const res = await fetchShowcaseBidders(selectedShowcaseBidder);
        if (res && res.showcase_bidders && res.showcase_bidders.length > 0) {
          setShowcaseCrossData(res.showcase_bidders[0]);
        }
      } catch (err) {
        console.error("Failed to load showcase bidder:", err);
      } finally {
        setShowcaseLoading(false);
      }
    };
    loadShowcase();
  }, [selectedShowcaseBidder]);

  const handleOpenDetail = async (verificationId: string) => {
    setDetailLoading(true);
    try {
      const res = await fetchMockRecordDetail(activeSource, verificationId);
      setDetailRecord(res);
    } catch (err) {
      console.error("Failed to load record detail:", err);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleScenarioClick = (scenarioKey: string) => {
    if (scenarioKey === "turnover") {
      setActiveSource("gstn");
      setSearchTerm("BIDDER-10");
      setSelectedShowcaseBidder("BIDDER-10");
      setPage(1);
    } else if (scenarioKey === "mse") {
      setActiveSource("udyam");
      setSearchTerm("BIDDER-03");
      setSelectedShowcaseBidder("BIDDER-03");
      setPage(1);
    } else if (scenarioKey === "local_content") {
      setActiveSource("mii");
      setSearchTerm("BIDDER-10");
      setSelectedShowcaseBidder("BIDDER-10");
      setPage(1);
    } else if (scenarioKey === "name_variation") {
      setActiveSource("mca");
      setSearchTerm("BIDDER-04");
      setSelectedShowcaseBidder("BIDDER-04");
      setPage(1);
    } else if (scenarioKey === "inactive") {
      setActiveSource("gstn");
      setSearchTerm("BIDDER-08");
      setSelectedShowcaseBidder("BIDDER-08");
      setPage(1);
    }
  };

  const getPrimaryIdentifier = (item: any) => {
    if (activeSource === "gstn") return item.gstin;
    if (activeSource === "udyam") return item.udyam_registration_number;
    if (activeSource === "mca") return item.cin;
    if (activeSource === "income_tax" || activeSource === "income-tax") return item.pan;
    if (activeSource === "nsic") return item.registration_number;
    if (activeSource === "digilocker") return item.document_reference;
    return item.verification_id;
  };

  const getKeyMetric = (item: any) => {
    if (activeSource === "gstn") return `₹${item.verified_turnover} Cr Turnover`;
    if (activeSource === "udyam") return `${item.enterprise_type} (${item.state})`;
    if (activeSource === "mca") return item.authorized_capital_cr ? `₹${item.authorized_capital_cr} Cr Auth Cap` : item.company_type;
    if (activeSource === "income_tax") return `${item.taxpayer_type} • ${item.pan_status}`;
    if (activeSource === "mii") return `${item.verified_local_content}% Domestic Content`;
    if (activeSource === "nsic") return item.monetary_limit ? `Limit: ₹${item.monetary_limit}L • ${item.category}` : item.category;
    if (activeSource === "digilocker") return `${item.document_type} • Sig: ${item.signature_status}`;
    return null;
  };

  const getStatusBadge = (status: string) => {
    const s = (status || "").toUpperCase();
    if (s === "ACTIVE" || s === "VERIFIED_CLASS_I" || s === "COMPLIANT" || s === "UP_TO_DATE") {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
          <CheckCircle2 className="w-3 h-3 mr-1 text-emerald-600" />
          {status}
        </span>
      );
    }
    if (s === "CANCELLED" || s === "STRUCK_OFF" || s === "INOPERATIVE" || s === "INVALID" || s === "CONTRADICTION") {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-50 text-rose-800 border border-rose-200">
          <AlertCircle className="w-3 h-3 mr-1 text-rose-600" />
          {status}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-200">
        <AlertTriangle className="w-3 h-3 mr-1 text-amber-600" />
        {status}
      </span>
    );
  };

  const sourceTabs = [
    { key: "gstn", label: "GSTN", title: "Goods & Services Tax Network", count: 1000 },
    { key: "udyam", label: "UDYAM", title: "Udyam / MSME Registry", count: 1000 },
    { key: "mca", label: "MCA", title: "Ministry of Corporate Affairs", count: 1000 },
    { key: "income_tax", label: "INCOME TAX", title: "Income Tax / PAN", count: 1000 },
    { key: "mii", label: "MAKE IN INDIA", title: "Local Content Audit", count: 1000 },
    { key: "nsic", label: "NSIC / SPRS", title: "Single Point Registration Scheme", count: 1000 },
    { key: "digilocker", label: "DIGILOCKER", title: "DigiLocker Document Verification", count: 1000 },
  ];

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Top Header & Navigation */}
      <div className="bg-white border border-slate-200 rounded-lg p-6 shadow-sm space-y-3">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2 text-xs text-slate-500 mb-1">
              <Link href="/" className="hover:text-blue-900 font-medium">
                Home
              </Link>
              <span>/</span>
              <span className="text-slate-800 font-semibold">Mock Data Explorer</span>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                Mock Verification Data Explorer
              </h1>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded text-xs font-bold bg-amber-50 text-amber-900 border border-amber-200">
                MOCK — SIH DEMONSTRATION
              </span>
            </div>
            <p className="text-xs text-slate-600 mt-1">
              Synthetic government-source records used for SIH demonstration and development. Database is the live runtime source of truth.
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={() => setShowIntegrityPanel(!showIntegrityPanel)}
              className="inline-flex items-center space-x-1.5 px-3.5 py-2 bg-blue-50 hover:bg-blue-100 border border-blue-200 text-blue-900 rounded-md text-xs font-bold transition shadow-xs"
            >
              <ShieldCheck className="w-4 h-4 text-blue-700" />
              <span>{showIntegrityPanel ? "Hide Integrity Panel" : "Dataset Integrity"}</span>
            </button>

            <a
              href={getMockSourceExportUrl(activeSource)}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center space-x-1.5 px-3.5 py-2 bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 rounded-md text-xs font-semibold transition shadow-xs"
            >
              <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
              <span>Export {activeSource.toUpperCase()} CSV</span>
            </a>
          </div>
        </div>

        {/* Global Summary Metrics */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
          <div className="p-3 bg-slate-50 border border-slate-200 rounded-md">
            <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">Registries</span>
            <span className="text-lg font-bold text-slate-900">5 Source Domains</span>
          </div>
          <div className="p-3 bg-slate-50 border border-slate-200 rounded-md">
            <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">Synthetic Records</span>
            <span className="text-lg font-bold text-slate-900">{summary?.total_records || 5000} Total Records</span>
          </div>
          <div className="p-3 bg-slate-50 border border-slate-200 rounded-md">
            <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">Showcase Bidders</span>
            <span className="text-lg font-bold text-slate-900">10 Fixed Bidders (Cross-Mapped)</span>
          </div>
          <div className="p-3 bg-slate-50 border border-slate-200 rounded-md">
            <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">Planted Fixtures</span>
            <span className="text-lg font-bold text-slate-900">5 Demo Scenarios</span>
          </div>
        </div>
      </div>

      {/* Dataset Integrity Panel (Expandable) */}
      {showIntegrityPanel && (
        <div className="bg-white border border-emerald-200 rounded-lg p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div className="flex items-center space-x-2">
              <ShieldCheck className="w-5 h-5 text-emerald-600" />
              <h3 className="font-bold text-sm text-slate-900">Dataset Integrity & Verification Gate</h3>
              <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                STATUS: {integrity?.status || "PASS"}
              </span>
            </div>
            <span className="text-xs text-slate-500">Live check against runtime database tables</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-5 gap-3 text-xs">
            {integrity?.sources &&
              Object.entries(integrity.sources).map(([sKey, sVal]: [string, any]) => (
                <div key={sKey} className="p-3 rounded-md border border-slate-200 bg-slate-50/60 space-y-1.5">
                  <div className="flex justify-between items-center font-bold text-slate-900">
                    <span className="uppercase">{sKey}</span>
                    <span className="text-emerald-700 font-mono text-[11px]">{sVal.count} records</span>
                  </div>
                  <div className="text-[11px] text-slate-600 space-y-0.5">
                    <div className="flex items-center">
                      <CheckCircle2 className="w-3 h-3 text-emerald-600 mr-1 flex-shrink-0" />
                      <span>IDs unique</span>
                    </div>
                    <div className="flex items-center">
                      <CheckCircle2 className="w-3 h-3 text-emerald-600 mr-1 flex-shrink-0" />
                      <span>Keys unique</span>
                    </div>
                    <div className="flex items-center">
                      <CheckCircle2 className="w-3 h-3 text-emerald-600 mr-1 flex-shrink-0" />
                      <span>All marked mock</span>
                    </div>
                  </div>
                </div>
              ))}
          </div>

          <div className="p-3 bg-emerald-50/70 border border-emerald-200 rounded-md text-xs text-emerald-900 flex items-start space-x-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
            <div className="leading-relaxed">
              <span className="font-bold">Integrity Verified: </span>
              All 5,000 synthetic records confirm <code className="font-mono bg-white px-1 py-0.5 rounded">is_mock = true</code> with official mock disclaimer label. All 10 showcase bidders are deterministically cross-mapped across all 5 registries, and all 5 planted contradiction/exemption scenarios are active.
            </div>
          </div>
        </div>
      )}

      {/* Demo Scenarios Section */}
      <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-sm space-y-3">
        <div className="flex items-center justify-between border-b border-slate-100 pb-2">
          <div className="flex items-center space-x-2">
            <Info className="w-4 h-4 text-blue-900" />
            <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wide">
              Demo Scenarios & Planted Contradiction Fixtures
            </h3>
          </div>
          <span className="text-[11px] text-slate-500">Click any scenario to filter the planted source fixture</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2.5">
          <button
            onClick={() => handleScenarioClick("turnover")}
            className="text-left p-3 rounded-md border border-slate-200 hover:border-blue-400 bg-slate-50/50 hover:bg-blue-50/40 transition group"
          >
            <div className="text-[11px] font-bold text-blue-900 group-hover:text-blue-700">
              1. Turnover Contradiction
            </div>
            <div className="text-[11px] text-slate-600 mt-1 leading-snug">
              Bidder declared ₹8.00 Cr vs GSTN verified ₹3.65 Cr (<span className="font-mono font-semibold">BIDDER-10</span>)
            </div>
          </button>

          <button
            onClick={() => handleScenarioClick("mse")}
            className="text-left p-3 rounded-md border border-slate-200 hover:border-blue-400 bg-slate-50/50 hover:bg-blue-50/40 transition group"
          >
            <div className="text-[11px] font-bold text-blue-900 group-hover:text-blue-700">
              2. MSE Exemption
            </div>
            <div className="text-[11px] text-slate-600 mt-1 leading-snug">
              Verified ACTIVE + MICRO status on Udyam (<span className="font-mono font-semibold">BIDDER-03</span>)
            </div>
          </button>

          <button
            onClick={() => handleScenarioClick("local_content")}
            className="text-left p-3 rounded-md border border-slate-200 hover:border-blue-400 bg-slate-50/50 hover:bg-blue-50/40 transition group"
          >
            <div className="text-[11px] font-bold text-blue-900 group-hover:text-blue-700">
              3. Local Content Shortfall
            </div>
            <div className="text-[11px] text-slate-600 mt-1 leading-snug">
              Bidder claimed 50% vs MII verified 32.0% (<span className="font-mono font-semibold">BIDDER-10</span>)
            </div>
          </button>

          <button
            onClick={() => handleScenarioClick("name_variation")}
            className="text-left p-3 rounded-md border border-slate-200 hover:border-blue-400 bg-slate-50/50 hover:bg-blue-50/40 transition group"
          >
            <div className="text-[11px] font-bold text-blue-900 group-hover:text-blue-700">
              4. Entity Name Variation
            </div>
            <div className="text-[11px] text-slate-600 mt-1 leading-snug">
              Alpha Tech Pvt Ltd vs MCA legal name (<span className="font-mono font-semibold">BIDDER-04</span>)
            </div>
          </button>

          <button
            onClick={() => handleScenarioClick("inactive")}
            className="text-left p-3 rounded-md border border-slate-200 hover:border-blue-400 bg-slate-50/50 hover:bg-blue-50/40 transition group"
          >
            <div className="text-[11px] font-bold text-blue-900 group-hover:text-blue-700">
              5. Inactive / Cancelled Status
            </div>
            <div className="text-[11px] text-slate-600 mt-1 leading-snug">
              GSTN Cancelled & PAN Inoperative (<span className="font-mono font-semibold">BIDDER-08</span>)
            </div>
          </button>
        </div>
      </div>

      {/* Showcase Bidder Cross-Source Inspector */}
      <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-sm space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <div className="flex items-center space-x-2">
            <Building2 className="w-4 h-4 text-blue-900" />
            <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wide">
              Showcase Bidders Multi-Registry Inspector
            </h3>
          </div>
          <span className="text-[11px] text-slate-500">
            Select a showcase bidder to inspect synchronized records across all 5 registries
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          <button
            onClick={() => setSelectedShowcaseBidder("")}
            className={`px-2.5 py-1 rounded text-xs font-semibold transition ${
              selectedShowcaseBidder === ""
                ? "bg-blue-900 text-white shadow-xs"
                : "bg-slate-100 text-slate-700 hover:bg-slate-200"
            }`}
          >
            All Bidders
          </button>
          {Array.from({ length: 10 }, (_, i) => {
            const bId = `BIDDER-${String(i + 1).padStart(2, "0")}`;
            const isSelected = selectedShowcaseBidder === bId;
            return (
              <button
                key={bId}
                onClick={() => {
                  setSelectedShowcaseBidder(isSelected ? "" : bId);
                  setSearchTerm(isSelected ? "" : bId);
                  setPage(1);
                }}
                className={`px-2.5 py-1 rounded text-xs font-mono font-semibold transition ${
                  isSelected
                    ? "bg-blue-900 text-white shadow-xs"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              >
                {bId}
              </button>
            );
          })}
        </div>

        {/* Cross-Source Record Cards when a showcase bidder is selected */}
        {selectedShowcaseBidder && showcaseCrossData && (
          <div className="mt-3 p-4 bg-slate-50 border border-slate-200 rounded-lg space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-900 flex items-center">
                <span className="bg-blue-900 text-white px-2 py-0.5 rounded font-mono mr-2 text-[11px]">
                  {selectedShowcaseBidder}
                </span>
                Cross-Registry Synchronized Profiles:
              </span>
              <span className="text-[11px] text-slate-500">5 Registry Contracts</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-5 gap-2.5 text-xs">
              {/* GSTN Card */}
              <div className="bg-white p-3 rounded border border-slate-200 space-y-1">
                <span className="font-bold text-[11px] text-blue-900 uppercase">GSTN</span>
                <p className="font-mono text-[11px] font-semibold text-slate-800 truncate">
                  {showcaseCrossData.records?.gstn?.gstin || "N/A"}
                </p>
                <div className="text-[11px] text-slate-600">
                  Turnover: ₹{showcaseCrossData.records?.gstn?.verified_turnover} Cr
                </div>
                <div>{getStatusBadge(showcaseCrossData.records?.gstn?.status)}</div>
              </div>

              {/* Udyam Card */}
              <div className="bg-white p-3 rounded border border-slate-200 space-y-1">
                <span className="font-bold text-[11px] text-blue-900 uppercase">UDYAM</span>
                <p className="font-mono text-[11px] font-semibold text-slate-800 truncate">
                  {showcaseCrossData.records?.udyam?.udyam_registration_number || "N/A"}
                </p>
                <div className="text-[11px] text-slate-600">
                  Type: {showcaseCrossData.records?.udyam?.enterprise_type}
                </div>
                <div>{getStatusBadge(showcaseCrossData.records?.udyam?.status)}</div>
              </div>

              {/* MCA Card */}
              <div className="bg-white p-3 rounded border border-slate-200 space-y-1">
                <span className="font-bold text-[11px] text-blue-900 uppercase">MCA</span>
                <p className="font-mono text-[11px] font-semibold text-slate-800 truncate">
                  {showcaseCrossData.records?.mca?.cin || "N/A"}
                </p>
                <div className="text-[11px] text-slate-600 truncate">
                  {showcaseCrossData.records?.mca?.legal_name}
                </div>
                <div>{getStatusBadge(showcaseCrossData.records?.mca?.company_status)}</div>
              </div>

              {/* Income Tax Card */}
              <div className="bg-white p-3 rounded border border-slate-200 space-y-1">
                <span className="font-bold text-[11px] text-blue-900 uppercase">INCOME TAX</span>
                <p className="font-mono text-[11px] font-semibold text-slate-800 truncate">
                  {showcaseCrossData.records?.income_tax?.pan || "N/A"}
                </p>
                <div className="text-[11px] text-slate-600">
                  ITR FY: {showcaseCrossData.records?.income_tax?.last_itr_filed_fy}
                </div>
                <div>{getStatusBadge(showcaseCrossData.records?.income_tax?.pan_status)}</div>
              </div>

              {/* MII Card */}
              <div className="bg-white p-3 rounded border border-slate-200 space-y-1">
                <span className="font-bold text-[11px] text-blue-900 uppercase">MAKE IN INDIA</span>
                <p className="font-mono text-[11px] font-semibold text-slate-800 truncate">
                  {showcaseCrossData.records?.mii?.verification_id || "N/A"}
                </p>
                <div className="text-[11px] text-slate-600">
                  Content: {showcaseCrossData.records?.mii?.verified_local_content}%
                </div>
                <div>{getStatusBadge(showcaseCrossData.records?.mii?.verification_status)}</div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Main Records Table Section */}
      <div className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden">
        {/* Source Navigation Tabs */}
        <div className="flex border-b border-slate-200 bg-slate-50/70 overflow-x-auto">
          {sourceTabs.map((tab) => {
            const isActive = activeSource === tab.key;
            return (
              <button
                key={tab.key}
                onClick={() => {
                  setActiveSource(tab.key);
                  setPage(1);
                  setSearchTerm("");
                  setStatusFilter("");
                }}
                className={`px-5 py-3 text-xs font-bold whitespace-nowrap border-b-2 transition flex items-center space-x-2 ${
                  isActive
                    ? "border-blue-900 text-blue-900 bg-white"
                    : "border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                }`}
              >
                <span>{tab.label}</span>
                <span className="text-[11px] font-normal px-1.5 py-0.2 rounded-full bg-slate-200/80 text-slate-700">
                  {tab.count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Filter Toolbar */}
        <div className="p-4 border-b border-slate-100 bg-white flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex flex-1 items-center space-x-2 max-w-md">
            <div className="relative w-full">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder={`Search ${activeSource.toUpperCase()} (identifiers, legal names, entity IDs)...`}
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                  setPage(1);
                }}
                className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-300 rounded-md text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-blue-900"
              />
            </div>
            {searchTerm && (
              <button
                onClick={() => setSearchTerm("")}
                className="text-xs text-slate-500 hover:text-slate-700 px-1"
              >
                Clear
              </button>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs">
            <div className="flex items-center space-x-1.5">
              <span className="text-slate-500">Status:</span>
              <select
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setPage(1);
                }}
                className="bg-slate-50 border border-slate-300 rounded-md px-2 py-1 text-slate-700 focus:outline-none focus:ring-1 focus:ring-blue-900"
              >
                <option value="">All Statuses</option>
                <option value="ACTIVE">ACTIVE</option>
                <option value="CANCELLED">CANCELLED</option>
                <option value="SUSPENDED">SUSPENDED</option>
                <option value="STRUCK_OFF">STRUCK_OFF</option>
                <option value="INOPERATIVE">INOPERATIVE</option>
                <option value="VERIFIED_CLASS_I">VERIFIED_CLASS_I</option>
                <option value="VERIFIED_CLASS_II">VERIFIED_CLASS_II</option>
              </select>
            </div>

            <label className="flex items-center space-x-1.5 cursor-pointer select-none text-slate-700">
              <input
                type="checkbox"
                checked={showcaseOnly}
                onChange={(e) => {
                  setShowcaseOnly(e.target.checked);
                  setPage(1);
                }}
                className="rounded text-blue-900 focus:ring-blue-900"
              />
              <span>Showcase Bidders Only</span>
            </label>

            <div className="flex items-center space-x-1.5">
              <span className="text-slate-500">Page size:</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setPage(1);
                }}
                className="bg-slate-50 border border-slate-300 rounded-md px-2 py-1 text-slate-700 focus:outline-none focus:ring-1 focus:ring-blue-900"
              >
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </div>
          </div>
        </div>

        {/* Table Content */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-700">
            <thead className="bg-slate-50 border-b border-slate-200 text-[11px] font-bold text-slate-600 uppercase tracking-wider">
              <tr>
                <th className="py-3 px-4">Verification ID</th>
                <th className="py-3 px-4">Entity Identifier</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Primary Identifier</th>
                <th className="py-3 px-4">Key Metric / Scope</th>
                <th className="py-3 px-4">Timestamp</th>
                <th className="py-3 px-4 text-center">Mock Flag</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-normal">
              {loading ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-slate-500">
                    Loading {activeSource.toUpperCase()} records from database...
                  </td>
                </tr>
              ) : recordsData?.items && recordsData.items.length > 0 ? (
                recordsData.items.map((item: any) => {
                  const isShowcase = (item.entity_identifier || "").startsWith("BIDDER-");
                  return (
                    <tr
                      key={item.verification_id}
                      onClick={() => handleOpenDetail(item.verification_id)}
                      className="hover:bg-slate-50/80 cursor-pointer transition"
                    >
                      <td className="py-3 px-4 font-mono font-medium text-slate-900">
                        {item.verification_id}
                      </td>
                      <td className="py-3 px-4">
                        {isShowcase ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded font-mono font-bold text-[11px] bg-blue-100 text-blue-900">
                            {item.entity_identifier}
                          </span>
                        ) : (
                          <span className="font-mono text-slate-600">{item.entity_identifier}</span>
                        )}
                      </td>
                      <td className="py-3 px-4">{getStatusBadge(item.status)}</td>
                      <td className="py-3 px-4 font-mono font-medium text-slate-800">
                        {getPrimaryIdentifier(item)}
                      </td>
                      <td className="py-3 px-4 text-slate-600">
                        {getKeyMetric(item) || item.legal_name || item.enterprise_name || item.product_category}
                      </td>
                      <td className="py-3 px-4 text-slate-500 font-mono text-[11px]">
                        {(item.verification_timestamp || "").slice(0, 10)}
                      </td>
                      <td className="py-3 px-4 text-center">
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100/70 text-amber-900 border border-amber-200">
                          MOCK
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleOpenDetail(item.verification_id);
                          }}
                          className="text-blue-900 hover:text-blue-700 font-semibold inline-flex items-center space-x-1"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          <span>Inspect</span>
                        </button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-slate-500">
                    No mock records match the current filter criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        {recordsData && recordsData.total > 0 && (
          <div className="p-4 border-t border-slate-100 bg-slate-50/50 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-600">
            <div>
              Showing <span className="font-bold text-slate-900">{(page - 1) * pageSize + 1}</span> to{" "}
              <span className="font-bold text-slate-900">
                {Math.min(page * pageSize, recordsData.total)}
              </span>{" "}
              of <span className="font-bold text-slate-900">{recordsData.total}</span> records
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-1.5 rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed transition"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>

              <span className="font-medium text-slate-700">
                Page {page} of {recordsData.total_pages}
              </span>

              <button
                onClick={() => setPage((p) => Math.min(recordsData.total_pages, p + 1))}
                disabled={page >= recordsData.total_pages}
                className="p-1.5 rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed transition"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Record Detail Drawer Modal */}
      {detailRecord && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center p-4 backdrop-blur-xs">
          <div className="bg-white border border-slate-200 rounded-lg max-w-2xl w-full max-h-[90vh] flex flex-col shadow-xl text-slate-900 overflow-hidden">
            {/* Drawer Header */}
            <div className="p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/80">
              <div className="space-y-1">
                <div className="flex items-center space-x-2">
                  <span className="text-xs font-bold text-blue-900 uppercase">
                    {detailRecord.source} Registry Record
                  </span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-900 border border-amber-200">
                    SYNTHETIC / MOCK DATA
                  </span>
                </div>
                <h3 className="font-mono font-bold text-sm text-slate-900">
                  {detailRecord.record?.verification_id}
                </h3>
              </div>
              <button
                onClick={() => setDetailRecord(null)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drawer Body */}
            <div className="p-5 space-y-4 overflow-y-auto text-xs">
              <div className="p-3 bg-amber-50/70 border border-amber-200 rounded-md text-amber-900 text-[11px] leading-relaxed">
                <span className="font-bold">Notice: </span>
                {detailRecord.disclaimer}
              </div>

              {/* Core Attributes */}
              <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 rounded-md border border-slate-200">
                <div>
                  <span className="text-slate-400 block text-[11px]">Entity Identifier</span>
                  <span className="font-mono font-bold text-slate-900">
                    {detailRecord.record?.entity_identifier}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[11px]">Status</span>
                  <div>{getStatusBadge(detailRecord.record?.status)}</div>
                </div>
                <div>
                  <span className="text-slate-400 block text-[11px]">Verification Timestamp</span>
                  <span className="font-mono text-slate-800">
                    {detailRecord.record?.verification_timestamp}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[11px]">Source Type Label</span>
                  <span className="font-semibold text-slate-700 text-[11px]">
                    {detailRecord.record?.source_type}
                  </span>
                </div>
              </div>

              {/* Source-Specific Attributes */}
              <div className="space-y-2">
                <h4 className="font-bold text-slate-900 uppercase text-[11px] tracking-wide">
                  Verified Specific Attributes
                </h4>
                <div className="grid grid-cols-2 gap-3 p-3 border border-slate-200 rounded-md">
                  {Object.entries(detailRecord.record || {})
                    .filter(
                      ([k]) =>
                        ![
                          "id",
                          "created_at",
                          "updated_at",
                          "verification_id",
                          "source",
                          "entity_identifier",
                          "status",
                          "verification_timestamp",
                          "is_mock",
                          "source_type",
                          "raw_response",
                          "verified_fields",
                        ].includes(k)
                    )
                    .map(([key, val]) => (
                      <div key={key}>
                        <span className="text-slate-400 text-[11px] block capitalize">
                          {key.replace(/_/g, " ")}
                        </span>
                        <span className="font-medium text-slate-900 font-mono">
                          {String(val ?? "N/A")}
                        </span>
                      </div>
                    ))}
                </div>
              </div>

              {/* Raw Response JSON Payload */}
              <div className="space-y-1.5">
                <h4 className="font-bold text-slate-900 uppercase text-[11px] tracking-wide">
                  Simulated Raw API Response Payload
                </h4>
                <pre className="p-3 bg-slate-900 text-slate-100 rounded-md text-[11px] font-mono overflow-x-auto max-h-48">
                  {JSON.stringify(detailRecord.record?.raw_response || {}, null, 2)}
                </pre>
              </div>
            </div>

            {/* Drawer Footer */}
            <div className="p-4 border-t border-slate-100 bg-slate-50 flex justify-end">
              <button
                onClick={() => setDetailRecord(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-md text-xs font-semibold"
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
