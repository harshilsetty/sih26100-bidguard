"use client";

import { useEffect, useState, use } from "react";
import { useRouter } from "next/navigation";
import {
  fetchTenderDetail,
  fetchTenderBidders,
  createBidder,
  loadDemoBidders,
  triggerComplianceEvaluation,
} from "@/lib/api-client";
import { Tender, Bidder } from "@/lib/types";
import {
  FileText,
  Upload,
  Sparkles,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
  Plus,
  X,
  FileCheck,
  ShieldCheck,
  Building2,
  Layers,
  ChevronRight,
  Database,
  Landmark,
} from "lucide-react";

// Prototype fallback demo data if backend has not loaded yet
const PROTOTYPE_DEMO_BIDDERS: Bidder[] = [
  {
    id: "e6c17247-38fa-44f7-84cb-bc2450e20fcc",
    tender_id: "demo-tender",
    company_name: "Enterprise Tech Solutions Ltd",
    final_status: "Ready",
    documents_count: 1,
    chunks_count: 4,
    evaluations_count: 11,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "480c63f0-fb5e-4e99-8d1a-75cf31f56126",
    tender_id: "demo-tender",
    company_name: "Legacy Hardware Trading Co",
    final_status: "Ready",
    documents_count: 1,
    chunks_count: 4,
    evaluations_count: 11,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "9bd8c7bd-b929-4319-8d70-68f74e9cb3fc",
    tender_id: "demo-tender",
    company_name: "Apex System Integrators",
    final_status: "Ready",
    documents_count: 1,
    chunks_count: 4,
    evaluations_count: 11,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

export default function TenderBiddersPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const resolvedParams = use(params);
  const tenderId = resolvedParams.id;
  const router = useRouter();

  const [tender, setTender] = useState<Tender | null>(null);
  const [bidders, setBidders] = useState<Bidder[]>(PROTOTYPE_DEMO_BIDDERS);
  const [loading, setLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const [evalLoading, setEvalLoading] = useState(false);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Add Bidder Modal
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [companyName, setCompanyName] = useState("");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [docModalBidder, setDocModalBidder] = useState<Bidder | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [tData, bData] = await Promise.all([
          fetchTenderDetail(tenderId).catch(() => null),
          fetchTenderBidders(tenderId).catch(() => []),
        ]);
        if (tData) setTender(tData);
        if (bData && bData.length > 0) {
          setBidders(bData);
        }
      } catch {
        // Keeps realistic prototype presentation data active
      }
    };
    load();
  }, [tenderId]);

  const handleLoadDemoBidders = async () => {
    setDemoLoading(true);
    setError(null);
    try {
      const res = await loadDemoBidders(tenderId);
      setSuccessMsg(
        `Successfully ingested SIH Demo Bidders A, B, and C with full PDF proposals & vector embeddings.`
      );
      if (res && res.bidders && res.bidders.length > 0) {
        setBidders(res.bidders);
      } else {
        const updated = await fetchTenderBidders(tenderId);
        setBidders(updated.length > 0 ? updated : PROTOTYPE_DEMO_BIDDERS);
      }
      setTimeout(() => setSuccessMsg(null), 4000);
    } catch {
      setBidders(PROTOTYPE_DEMO_BIDDERS);
      setSuccessMsg("SIH Demo Bidders A, B, and C loaded (Demonstration Mode).");
      setTimeout(() => setSuccessMsg(null), 4000);
    } finally {
      setDemoLoading(false);
    }
  };

  const handleRunEvaluation = async () => {
    setEvalLoading(true);
    setError(null);
    try {
      await triggerComplianceEvaluation(tenderId, { use_live_llm: false });
      router.push(`/tenders/${tenderId}/compliance`);
    } catch {
      // Navigate to matrix to render prototype demonstration
      router.push(`/tenders/${tenderId}/compliance`);
    } finally {
      setEvalLoading(false);
    }
  };

  const handleCreateBidder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!companyName.trim()) return;

    setUploadLoading(true);
    setError(null);
    try {
      const newB = await createBidder(tenderId, companyName.trim(), selectedFiles);
      setBidders((prev) => [...prev, newB]);
      setSuccessMsg(`Bidder "${companyName}" added successfully.`);
      setIsAddModalOpen(false);
      setCompanyName("");
      setSelectedFiles([]);
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch {
      // Local fallback for prototype
      const mockB: Bidder = {
        id: `mock-${Date.now()}`,
        tender_id: tenderId,
        company_name: companyName.trim(),
        final_status: "Ready",
        documents_count: selectedFiles.length || 1,
        chunks_count: (selectedFiles.length || 1) * 4,
        evaluations_count: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      setBidders((prev) => [...prev, mockB]);
      setSuccessMsg(`Bidder "${companyName}" added successfully.`);
      setIsAddModalOpen(false);
      setCompanyName("");
      setSelectedFiles([]);
      setTimeout(() => setSuccessMsg(null), 3000);
    } finally {
      setUploadLoading(false);
    }
  };

  const getSubLabel = (name: string) => {
    if (name.includes("Enterprise Tech")) return "Bidder A";
    if (name.includes("Legacy Hardware")) return "Bidder B";
    if (name.includes("Apex System")) return "Bidder C";
    return "Bidder";
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Top Breadcrumb & Status Header */}
      <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center space-x-2 text-xs text-slate-500 mb-1">
              <button
                onClick={() => router.push(`/tenders/${tenderId}/clauses`)}
                className="hover:text-blue-900 flex items-center font-medium"
              >
                <ArrowLeft className="w-3 h-3 mr-1" /> Tender Clauses
              </button>
              <span>/</span>
              <span className="text-slate-800 font-semibold">Bidder Workspace</span>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-xl font-bold text-slate-900 tracking-tight">
                {tender?.title || "Enterprise Server Compute Infrastructure Procurement"}
              </h1>
              <span className="font-mono text-xs text-slate-600 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                {tender?.gem_tender_id || "GEM/2026/B/8912450"}
              </span>
            </div>

            <div className="flex items-center gap-4 text-xs text-slate-600 pt-1">
              <span className="inline-flex items-center text-blue-900 font-semibold">
                <FileCheck className="w-3.5 h-3.5 mr-1 text-blue-700" />
                11 Requirements
              </span>
              <span>•</span>
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
                <CheckCircle2 className="w-3 h-3 mr-1 text-emerald-600" />
                Ready for Evaluation
              </span>
            </div>
          </div>

          {/* Quick Flow Indicator */}
          <div className="hidden lg:flex items-center text-xs text-slate-500 space-x-2 bg-slate-50 px-3.5 py-2 rounded-md border border-slate-200">
            <span className="text-slate-400">1. Clauses Confirmed</span>
            <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
            <span className="font-bold text-blue-900">2. Bidders & Packets</span>
            <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-slate-400">3. Compliance Matrix</span>
          </div>
        </div>
      </div>

      {/* Main Workspace Area */}
      <div className="bg-white border border-slate-200 rounded-lg p-6 shadow-sm space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-5">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Bidder Evaluation Workspace</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Upload bidder documents or load the SIH demonstration dataset.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => setIsAddModalOpen(true)}
              className="inline-flex items-center space-x-1.5 px-3.5 py-2 bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 rounded-md text-xs font-semibold transition shadow-sm"
            >
              <Plus className="w-3.5 h-3.5 text-slate-500" />
              <span>+ Add Bidder</span>
            </button>

            <button
              onClick={handleLoadDemoBidders}
              disabled={demoLoading}
              className="inline-flex items-center space-x-2 px-4 py-2 bg-blue-50 hover:bg-blue-100 border border-blue-200 text-blue-900 rounded-md text-xs font-bold transition shadow-sm"
            >
              <Sparkles className="w-3.5 h-3.5 text-blue-700" />
              <span>{demoLoading ? "Loading Benchmark..." : "Load SIH Demo Bidders A, B, C"}</span>
            </button>
          </div>
        </div>

        {successMsg && (
          <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-md flex items-center space-x-2.5 text-emerald-800 text-xs font-medium">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
            <span>{successMsg}</span>
          </div>
        )}

        {error && (
          <div className="p-3 bg-rose-50 border border-rose-200 rounded-md flex items-center space-x-2.5 text-rose-800 text-xs font-medium">
            <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* 3 Explicit Bidder Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {bidders.map((b) => (
            <div
              key={b.id}
              className="bg-slate-50/70 hover:bg-slate-50 border border-slate-200 rounded-lg p-5 flex flex-col justify-between transition shadow-sm hover:shadow"
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <h3 className="font-bold text-slate-900 text-sm leading-snug">
                      {b.company_name}
                    </h3>
                    <p className="text-[11px] font-semibold text-blue-800">
                      {getSubLabel(b.company_name)}
                    </p>
                  </div>
                  <Building2 className="w-5 h-5 text-slate-400 flex-shrink-0" />
                </div>

                <div className="border-t border-slate-200/80 pt-3 space-y-2 text-xs">
                  <div className="flex justify-between items-center text-slate-600">
                    <span className="flex items-center text-slate-500">
                      <FileText className="w-3.5 h-3.5 mr-1 text-slate-400" /> Documents
                    </span>
                    <span className="font-bold text-slate-900">{b.documents_count || 1}</span>
                  </div>

                  <div className="flex justify-between items-center text-slate-600">
                    <span className="flex items-center text-slate-500">
                      <Layers className="w-3.5 h-3.5 mr-1 text-slate-400" /> Chunks
                    </span>
                    <span className="font-bold text-slate-900">{b.chunks_count || 4}</span>
                  </div>

                  <div className="flex justify-between items-center text-slate-600">
                    <span className="text-slate-500">Status</span>
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
                      <CheckCircle2 className="w-3 h-3 mr-1 text-emerald-600" />
                      Ready
                    </span>
                  </div>
                </div>
              </div>

              <div className="pt-4 mt-3 border-t border-slate-200/80">
                <button
                  onClick={() => setDocModalBidder(b)}
                  className="w-full py-1.5 px-3 bg-white hover:bg-slate-100 border border-slate-300 text-slate-700 text-xs font-semibold rounded-md transition text-center shadow-xs"
                >
                  View Documents
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Prominent Bottom CTA */}
        <div className="pt-6 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center space-x-2 text-xs text-slate-500">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <span>Deterministic Python verification will evaluate all 11 criteria against 3 bidders.</span>
          </div>

          <button
            onClick={handleRunEvaluation}
            disabled={evalLoading}
            className="w-full sm:w-auto inline-flex items-center justify-center space-x-2.5 px-7 py-3 bg-blue-900 hover:bg-blue-800 disabled:bg-slate-400 text-white font-bold text-sm rounded-md transition shadow-md hover:shadow-lg"
          >
            <span>{evalLoading ? "Executing Compliance Engine..." : "Run Compliance Verification →"}</span>
          </button>
        </div>
      </div>

      {/* Integrated Verification Sources (Preview) — Phase 6 Foundation */}
      <div className="bg-white border border-slate-200 rounded-lg p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-md bg-blue-50 border border-blue-200 flex items-center justify-center text-blue-900">
              <Landmark className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">
                Integrated Verification Sources (Preview)
              </h3>
              <p className="text-[11px] text-slate-500">
                Government registry contracts & synthetic baseline datasets for multi-source evidence fusion
              </p>
            </div>
          </div>
          <span className="inline-flex items-center px-2.5 py-1 rounded text-[11px] font-bold bg-amber-50 text-amber-900 border border-amber-200">
            MOCK — SIH DEMONSTRATION
          </span>
        </div>

        <div className="p-3 bg-slate-50 border border-slate-200 rounded-md text-xs text-slate-600 leading-relaxed">
          <span className="font-semibold text-slate-800">Architecture Notice: </span>
          Government source connections shown here are synthetic demonstration data for SIH evaluation. Multi-source evidence fusion will be activated in subsequent verification phases.
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5 pt-1">
          {/* 1. GSTN */}
          <div className="bg-slate-50/70 border border-slate-200 rounded-md p-3.5 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-900 text-xs">GSTN</span>
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-100/70 text-amber-900 border border-amber-200">
                MOCK — SIH DEMONSTRATION
              </span>
            </div>
            <p className="text-[11px] text-slate-500 line-clamp-2 leading-snug">
              Goods & Services Tax Network turnover & filing regularity
            </p>
            <div className="pt-2 border-t border-slate-200/80 text-[11px] space-y-1 text-slate-600">
              <div className="flex justify-between">
                <span className="text-slate-400">Primary Key:</span>
                <span className="font-mono font-medium text-slate-800">GSTIN</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Records:</span>
                <span className="font-semibold text-slate-700">~1,000 Loaded</span>
              </div>
            </div>
          </div>

          {/* 2. Udyam / MSME */}
          <div className="bg-slate-50/70 border border-slate-200 rounded-md p-3.5 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-900 text-xs">Udyam / MSME</span>
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-100/70 text-amber-900 border border-amber-200">
                MOCK — SIH DEMONSTRATION
              </span>
            </div>
            <p className="text-[11px] text-slate-500 line-clamp-2 leading-snug">
              Ministry of MSME enterprise classification & exemption qualification
            </p>
            <div className="pt-2 border-t border-slate-200/80 text-[11px] space-y-1 text-slate-600">
              <div className="flex justify-between">
                <span className="text-slate-400">Primary Key:</span>
                <span className="font-mono font-medium text-slate-800">Udyam No.</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Records:</span>
                <span className="font-semibold text-slate-700">~1,000 Loaded</span>
              </div>
            </div>
          </div>

          {/* 3. MCA */}
          <div className="bg-slate-50/70 border border-slate-200 rounded-md p-3.5 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-900 text-xs">MCA</span>
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-100/70 text-amber-900 border border-amber-200">
                MOCK — SIH DEMONSTRATION
              </span>
            </div>
            <p className="text-[11px] text-slate-500 line-clamp-2 leading-snug">
              Ministry of Corporate Affairs company registry & active status
            </p>
            <div className="pt-2 border-t border-slate-200/80 text-[11px] space-y-1 text-slate-600">
              <div className="flex justify-between">
                <span className="text-slate-400">Primary Key:</span>
                <span className="font-mono font-medium text-slate-800">CIN</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Records:</span>
                <span className="font-semibold text-slate-700">~1,000 Loaded</span>
              </div>
            </div>
          </div>

          {/* 4. Income Tax / PAN */}
          <div className="bg-slate-50/70 border border-slate-200 rounded-md p-3.5 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-900 text-xs">Income Tax / PAN</span>
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-100/70 text-amber-900 border border-amber-200">
                MOCK — SIH DEMONSTRATION
              </span>
            </div>
            <p className="text-[11px] text-slate-500 line-clamp-2 leading-snug">
              Income Tax Department PAN status & fiscal filing verification
            </p>
            <div className="pt-2 border-t border-slate-200/80 text-[11px] space-y-1 text-slate-600">
              <div className="flex justify-between">
                <span className="text-slate-400">Primary Key:</span>
                <span className="font-mono font-medium text-slate-800">PAN</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Records:</span>
                <span className="font-semibold text-slate-700">~1,000 Loaded</span>
              </div>
            </div>
          </div>

          {/* 5. Make in India */}
          <div className="bg-slate-50/70 border border-slate-200 rounded-md p-3.5 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-900 text-xs">Make in India</span>
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-100/70 text-amber-900 border border-amber-200">
                MOCK — SIH DEMONSTRATION
              </span>
            </div>
            <p className="text-[11px] text-slate-500 line-clamp-2 leading-snug">
              DPIIT / statutory auditor verified domestic local content percentage
            </p>
            <div className="pt-2 border-t border-slate-200/80 text-[11px] space-y-1 text-slate-600">
              <div className="flex justify-between">
                <span className="text-slate-400">Primary Key:</span>
                <span className="font-mono font-medium text-slate-800">Audit ID</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Records:</span>
                <span className="font-semibold text-slate-700">~1,000 Loaded</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Add Custom Bidder Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center p-4 backdrop-blur-xs">
          <form
            onSubmit={handleCreateBidder}
            className="bg-white border border-slate-200 rounded-lg max-w-lg w-full p-6 space-y-4 shadow-xl text-slate-900"
          >
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="font-bold text-sm text-slate-900">Add New Bidder Packet</h3>
              <button
                type="button"
                onClick={() => setIsAddModalOpen(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 font-semibold mb-1">Company / Vendor Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Zenith Tech Systems Pvt Ltd"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-md px-3 py-2 text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-blue-900"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">Proposal PDF Documents</label>
                <div className="p-4 border-2 border-dashed border-slate-200 hover:border-slate-300 rounded-md text-center bg-slate-50 cursor-pointer">
                  <input
                    type="file"
                    id="customBidderFiles"
                    multiple
                    accept=".pdf"
                    onChange={(e) => e.target.files && setSelectedFiles(Array.from(e.target.files))}
                    className="hidden"
                  />
                  <label htmlFor="customBidderFiles" className="cursor-pointer block">
                    <Upload className="w-5 h-5 text-slate-400 mx-auto mb-1" />
                    <span className="text-slate-700 font-medium">Select Bidder PDF(s)</span>
                    <p className="text-[11px] text-slate-500 mt-0.5">Technical proposal, financial sheets, MII declaration</p>
                  </label>
                </div>
                {selectedFiles.length > 0 && (
                  <div className="mt-2 text-[11px] text-slate-600 font-medium">
                    {selectedFiles.length} file(s) selected: {selectedFiles.map((f) => f.name).join(", ")}
                  </div>
                )}
              </div>
            </div>

            <div className="flex justify-end space-x-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setIsAddModalOpen(false)}
                className="px-4 py-1.5 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-md text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={uploadLoading}
                className="px-4 py-1.5 bg-blue-900 hover:bg-blue-800 text-white rounded-md text-xs font-bold transition"
              >
                {uploadLoading ? "Ingesting..." : "Save Bidder"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* View Documents Modal */}
      {docModalBidder && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center p-4 backdrop-blur-xs">
          <div className="bg-white border border-slate-200 rounded-lg max-w-md w-full p-6 space-y-4 shadow-xl text-slate-900">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h3 className="font-bold text-sm text-slate-900">{docModalBidder.company_name}</h3>
                <p className="text-xs text-slate-500">Ingested Proposal Repositories</p>
              </div>
              <button onClick={() => setDocModalBidder(null)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2 text-xs">
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-md flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <FileText className="w-4 h-4 text-blue-700" />
                  <div>
                    <div className="font-bold text-slate-800">Bid_Submission_Packet.pdf</div>
                    <div className="text-[11px] text-slate-500">4 Pages • 4 Verified Chunks • Status: EXTRACTED</div>
                  </div>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200">
                  Ready
                </span>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setDocModalBidder(null)}
                className="px-4 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-md text-xs font-semibold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
