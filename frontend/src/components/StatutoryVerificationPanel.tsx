"use client";

import React, { useState } from "react";
import {
  StatutoryAuthority,
  SourceVerificationResult,
  BidderStatutoryVerificationSummary,
  Bidder,
} from "@/lib/types";
import { verifyStatutorySources } from "@/lib/api-client";
import {
  ShieldCheck,
  Building2,
  FileCheck,
  Landmark,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  ExternalLink,
  Calendar,
} from "lucide-react";

interface StatutoryVerificationPanelProps {
  tenderId: string;
  bidders: Bidder[];
}

export default function StatutoryVerificationPanel({
  tenderId,
  bidders,
}: StatutoryVerificationPanelProps) {
  const [selectedBidderId, setSelectedBidderId] = useState<string>(
    bidders.length > 0 ? bidders[0].id : ""
  );
  const [asOfDate, setAsOfDate] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [summary, setSummary] = useState<BidderStatutoryVerificationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleVerify = async () => {
    if (!selectedBidderId) return;
    setLoading(true);
    setError(null);

    const selectedBidder = bidders.find((b) => b.id === selectedBidderId);

    try {
      const res = await verifyStatutorySources({
        tender_id: tenderId,
        bidder_id: selectedBidderId,
        as_of_date: asOfDate ? asOfDate : null,
        identifiers: selectedBidder
          ? { company_name: selectedBidder.company_name }
          : {},
      });
      setSummary(res);
    } catch (err: any) {
      setError(err?.message || "Failed to execute statutory verification.");
    } finally {
      setLoading(false);
    }
  };

  const getConnectionBadge = (status: string) => {
    switch (status) {
      case "SUCCESS":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-3 h-3 mr-1" />
            CONN: SUCCESS
          </span>
        );
      case "TIMEOUT":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
            <Clock className="w-3 h-3 mr-1" />
            CONN: TIMEOUT
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
            <XCircle className="w-3 h-3 mr-1" />
            CONN: {status}
          </span>
        );
    }
  };

  const getVerificationBadge = (status: string) => {
    switch (status) {
      case "VERIFIED":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
            VERIFIED
          </span>
        );
      case "NOT_FOUND":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-300">
            NOT FOUND
          </span>
        );
      case "INACTIVE":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
            INACTIVE
          </span>
        );
      case "DISCREPANCY":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-300">
            DISCREPANCY
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
            {status}
          </span>
        );
    }
  };

  const getAuthorityIcon = (auth: StatutoryAuthority) => {
    switch (auth) {
      case "GSTN":
        return <Landmark className="w-4 h-4 text-blue-600" />;
      case "UDYAM":
        return <Building2 className="w-4 h-4 text-emerald-600" />;
      case "MCA":
        return <ShieldCheck className="w-4 h-4 text-purple-600" />;
      case "INCOME_TAX":
        return <FileCheck className="w-4 h-4 text-orange-600" />;
      case "MII":
        return <CheckCircle2 className="w-4 h-4 text-indigo-600" />;
      default:
        return <Landmark className="w-4 h-4 text-slate-600" />;
    }
  };

  const renderPayloadSummary = (result: SourceVerificationResult) => {
    const p = result.data_payload || {};
    if (!p || Object.keys(p).length === 0) {
      return (
        <span className="text-[11px] text-slate-400 italic">
          No factual payload recorded
        </span>
      );
    }

    switch (result.authority) {
      case "GSTN":
        return (
          <div className="space-y-1 text-[11px] text-slate-600">
            <div className="flex justify-between">
              <span className="text-slate-500">GSTIN:</span>
              <span className="font-mono font-bold text-slate-800">{p.gstin || "N/A"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Verified Turnover:</span>
              <span className="font-semibold text-slate-800">
                {p.verified_turnover ? `₹${p.verified_turnover.toFixed(2)} Cr` : "N/A"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Filing Status:</span>
              <span className="font-medium text-slate-700">{p.filing_status || "N/A"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">State:</span>
              <span className="text-slate-700">{p.state || "N/A"}</span>
            </div>
          </div>
        );

      case "UDYAM":
        return (
          <div className="space-y-1 text-[11px] text-slate-600">
            <div className="flex justify-between">
              <span className="text-slate-500">Registration:</span>
              <span className="font-mono font-bold text-slate-800">{p.udyam_registration_number || "N/A"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Enterprise Type:</span>
              <span className="font-semibold text-emerald-700">{p.enterprise_type || "N/A"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Activity:</span>
              <span className="text-slate-700">{p.major_activity || "N/A"}</span>
            </div>
          </div>
        );

      case "MCA":
        return (
          <div className="space-y-1 text-[11px] text-slate-600">
            <div className="flex justify-between">
              <span className="text-slate-500">CIN:</span>
              <span className="font-mono font-bold text-slate-800">{p.cin || "N/A"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Status:</span>
              <span className="font-semibold text-purple-700">{p.company_status || "N/A"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Auth Capital:</span>
              <span className="text-slate-700">
                {p.authorized_capital_cr ? `₹${p.authorized_capital_cr} Cr` : "N/A"}
              </span>
            </div>
          </div>
        );

      case "INCOME_TAX":
        return (
          <div className="space-y-1 text-[11px] text-slate-600">
            <div className="flex justify-between">
              <span className="text-slate-500">PAN:</span>
              <span className="font-mono font-bold text-slate-800">{p.pan || "N/A"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">PAN Status:</span>
              <span className="font-semibold text-slate-800">{p.pan_status || "N/A"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Last ITR FY:</span>
              <span className="text-slate-700">{p.last_itr_filed_fy || "N/A"}</span>
            </div>
          </div>
        );

      case "MII":
        return (
          <div className="space-y-1 text-[11px] text-slate-600">
            <div className="flex justify-between">
              <span className="text-slate-500">Local Content:</span>
              <span className="font-bold text-indigo-700">
                {p.verified_local_content !== undefined ? `${p.verified_local_content}%` : "N/A"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Certificate Ref:</span>
              <span className="font-mono text-slate-700">{p.certificate_reference || "N/A"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Authority:</span>
              <span className="text-slate-600 truncate max-w-[150px]">{p.certifying_authority || "N/A"}</span>
            </div>
          </div>
        );

      default:
        return (
          <div className="text-[10px] text-slate-500 truncate">
            {JSON.stringify(p)}
          </div>
        );
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-6 shadow-sm space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-lg bg-blue-50 border border-blue-200 flex items-center justify-center text-blue-900 shadow-xs">
            <Landmark className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-900">
              Statutory Verification Orchestrator
            </h3>
            <p className="text-xs text-slate-500">
              Authoritative multi-source register checks (GSTN, Udyam, MCA, Income Tax, MII)
            </p>
          </div>
        </div>

        <span className="inline-flex items-center px-2.5 py-1 rounded text-[11px] font-bold bg-amber-50 text-amber-900 border border-amber-200">
          MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION
        </span>
      </div>

      {/* Query Control Bar */}
      <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 flex flex-wrap items-center gap-4 text-xs">
        <div className="flex items-center space-x-2">
          <label className="font-semibold text-slate-700">Target Bidder:</label>
          <select
            value={selectedBidderId}
            onChange={(e) => setSelectedBidderId(e.target.value)}
            className="bg-white border border-slate-300 rounded px-3 py-1.5 text-slate-900 font-medium focus:outline-none focus:ring-1 focus:ring-blue-900"
          >
            {bidders.map((b) => (
              <option key={b.id} value={b.id}>
                {b.company_name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center space-x-2">
          <label className="font-semibold text-slate-700 flex items-center">
            <Calendar className="w-3.5 h-3.5 mr-1 text-slate-500" />
            As-of Date (Cutoff):
          </label>
          <input
            type="date"
            value={asOfDate}
            onChange={(e) => setAsOfDate(e.target.value)}
            className="bg-white border border-slate-300 rounded px-2.5 py-1 text-slate-900 focus:outline-none focus:ring-1 focus:ring-blue-900"
          />
        </div>

        <button
          onClick={handleVerify}
          disabled={loading || !selectedBidderId}
          className="ml-auto inline-flex items-center space-x-2 px-4 py-2 bg-blue-900 hover:bg-blue-800 disabled:bg-slate-300 text-white font-semibold rounded transition shadow-xs"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>{loading ? "Verifying Registers..." : "Run Statutory Verification"}</span>
        </button>
      </div>

      {error && (
        <div className="p-3 bg-rose-50 border border-rose-200 rounded-md text-xs text-rose-700 flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Verification Results Cards */}
      {summary ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs text-slate-500 px-1">
            <span>
              Verified {summary.total_sources} Authorities • {summary.successful_connections} Successful Connections
            </span>
            <span>
              Retrieved at: {new Date(summary.verified_at).toLocaleTimeString()}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3.5">
            {summary.results.map((r) => (
              <div
                key={r.verification_id}
                className="bg-white border border-slate-200 rounded-lg p-3.5 space-y-2.5 shadow-xs hover:border-slate-300 transition"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-1.5">
                    {getAuthorityIcon(r.authority)}
                    <span className="font-bold text-slate-900 text-xs">{r.authority}</span>
                  </div>
                  {getConnectionBadge(r.connection_status)}
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-slate-500 font-medium truncate max-w-[110px]" title={r.source_name}>
                    {r.source_name}
                  </span>
                  {getVerificationBadge(r.verification_status)}
                </div>

                <div className="pt-2 border-t border-slate-100">
                  {renderPayloadSummary(r)}
                </div>

                <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-[10px] text-slate-400">
                  <span>Latency: {r.execution_time_ms}ms</span>
                  <span>Conf: {r.confidence_score.toFixed(1)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        /* Static / Baseline Preview before trigger */
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
          {[
            { name: "GSTN", label: "Goods & Services Tax", key: "GSTIN", desc: "Turnover, filing status & active registration" },
            { name: "Udyam / MSME", label: "Ministry of MSME", key: "Udyam No.", desc: "Enterprise scale (Micro/Small/Medium)" },
            { name: "MCA", label: "Corporate Affairs", key: "CIN", desc: "Active company status & authorized capital" },
            { name: "Income Tax", label: "CBDT PAN Register", key: "PAN", desc: "PAN validity & tax filing compliance" },
            { name: "Make in India", label: "DPIIT Local Content", key: "Audit Ref", desc: "Statutory verified domestic content %" },
          ].map((item, idx) => (
            <div key={idx} className="bg-slate-50/70 border border-slate-200 rounded-md p-3.5 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-900 text-xs">{item.name}</span>
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-100/70 text-amber-900 border border-amber-200">
                  MOCK
                </span>
              </div>
              <p className="text-[11px] text-slate-500 line-clamp-2 leading-snug">{item.desc}</p>
              <div className="pt-2 border-t border-slate-200/80 text-[11px] space-y-1 text-slate-600">
                <div className="flex justify-between">
                  <span className="text-slate-400">Primary Key:</span>
                  <span className="font-mono font-medium text-slate-800">{item.key}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Status:</span>
                  <span className="font-semibold text-emerald-700">Ready to Query</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
