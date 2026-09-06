"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchSystemHealth, fetchNvidiaHealth, fetchTenders } from "@/lib/api-client";
import { SystemHealth, NvidiaHealth, Tender } from "@/lib/types";
import {
  Activity,
  Database,
  Cpu,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  FileText,
  Plus,
  ArrowRight,
  SlidersHorizontal,
  Clock,
} from "lucide-react";

export default function HomePage() {
  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
  const [nvidiaHealth, setNvidiaHealth] = useState<NvidiaHealth | null>(null);
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const checkHealth = async () => {
    setLoading(true);
    try {
      const [sys, nvd, tnd] = await Promise.allSettled([
        fetchSystemHealth(),
        fetchNvidiaHealth(),
        fetchTenders(),
      ]);

      if (sys.status === "fulfilled") {
        setSystemHealth(sys.value);
      } else {
        setSystemHealth({
          status: "OFFLINE",
          service: "GeM Platform Backend",
          version: "0.1.0",
          database: "DISCONNECTED",
        });
      }

      if (nvd.status === "fulfilled") {
        setNvidiaHealth(nvd.value);
      } else {
        setNvidiaHealth({
          status: "OFFLINE",
          model: "openai/gpt-oss-20b",
          base_url: "https://integrate.api.nvidia.com/v1",
          message: "Could not reach NVIDIA health endpoint",
        });
      }

      if (tnd.status === "fulfilled") {
        setTenders(tnd.value);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkHealth();
  }, []);

  return (
    <div className="space-y-8">
      {/* Header Banner with CTA */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center space-x-2 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-950 text-blue-400 border border-blue-800 mb-2">
            <span>SIH26100 • GeM Procurement Evaluation</span>
          </div>
          <h2 className="text-2xl font-bold text-slate-100">
            Tender Compliance Verification Platform
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            PyMuPDF document extraction & NVIDIA NIM GPT-OSS 20B requirement parsing with human-in-the-loop confirmation.
          </p>
        </div>
        <div className="flex items-center space-x-3">
          <button
            onClick={checkHealth}
            disabled={loading}
            className="p-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs transition border border-slate-700"
            title="Refresh Diagnostics"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
          <Link
            href="/tenders/new"
            className="inline-flex items-center space-x-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition shadow-md shadow-blue-600/20"
          >
            <Plus className="w-4 h-4" />
            <span>Upload Tender</span>
          </Link>
        </div>
      </div>

      {/* Diagnostics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2 text-slate-300">
              <Activity className="w-5 h-5 text-blue-400" />
              <span className="font-medium text-sm">FastAPI Backend</span>
            </div>
            {systemHealth?.status === "HEALTHY" ? (
              <span className="inline-flex items-center text-xs font-medium text-emerald-400">
                <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Active
              </span>
            ) : (
              <span className="inline-flex items-center text-xs font-medium text-amber-400">
                <AlertCircle className="w-3.5 h-3.5 mr-1" /> {systemHealth?.status || "Checking"}
              </span>
            )}
          </div>
          <div className="text-xs text-slate-400 space-y-1">
            <p><span className="text-slate-500">Service:</span> {systemHealth?.service || "GeM Platform"}</p>
            <p><span className="text-slate-500">Version:</span> {systemHealth?.version || "0.1.0"}</p>
          </div>
        </div>

        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2 text-slate-300">
              <Database className="w-5 h-5 text-indigo-400" />
              <span className="font-medium text-sm">PostgreSQL Database</span>
            </div>
            {systemHealth?.database === "HEALTHY" ? (
              <span className="inline-flex items-center text-xs font-medium text-emerald-400">
                <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Connected
              </span>
            ) : (
              <span className="inline-flex items-center text-xs font-medium text-amber-400">
                <AlertCircle className="w-3.5 h-3.5 mr-1" /> {systemHealth?.database || "Offline"}
              </span>
            )}
          </div>
          <div className="text-xs text-slate-400 space-y-1">
            <p><span className="text-slate-500">Driver:</span> asyncpg (SQLAlchemy 2.0)</p>
            <p><span className="text-slate-500">pgvector:</span> Ready for Day 3 embeddings</p>
          </div>
        </div>

        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2 text-slate-300">
              <Cpu className="w-5 h-5 text-emerald-400" />
              <span className="font-medium text-sm">NVIDIA NIM LLM</span>
            </div>
            {nvidiaHealth?.status === "HEALTHY" ? (
              <span className="inline-flex items-center text-xs font-medium text-emerald-400">
                <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Ready
              </span>
            ) : (
              <span className="inline-flex items-center text-xs font-medium text-amber-400">
                <AlertCircle className="w-3.5 h-3.5 mr-1" /> {nvidiaHealth?.status || "Checking"}
              </span>
            )}
          </div>
          <div className="text-xs text-slate-400 space-y-1">
            <p><span className="text-slate-500">Model:</span> {nvidiaHealth?.model || "openai/gpt-oss-20b"}</p>
            <p><span className="text-slate-500">Latency:</span> {nvidiaHealth?.latency_ms ? `${nvidiaHealth.latency_ms} ms` : "N/A"}</p>
          </div>
        </div>
      </div>

      {/* Active Tenders List */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <FileText className="w-5 h-5 text-blue-400" />
            <h3 className="font-semibold text-sm text-slate-100">Active Tender Documents</h3>
          </div>
          <Link
            href="/tenders/new"
            className="text-xs text-blue-400 hover:text-blue-300 transition font-medium"
          >
            + Upload New
          </Link>
        </div>

        {tenders.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <FileText className="w-10 h-10 text-slate-600 mx-auto" />
            <p className="text-sm text-slate-400">No tenders ingested yet.</p>
            <p className="text-xs text-slate-500">
              Upload a GeM Tender Notice / NIT document to trigger AI requirement extraction.
            </p>
            <div className="pt-2">
              <Link
                href="/tenders/new"
                className="inline-flex items-center space-x-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-medium transition"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Upload First Tender</span>
              </Link>
            </div>
          </div>
        ) : (
          <div className="divide-y divide-slate-800/60">
            {tenders.map((tender) => (
              <div
                key={tender.id}
                className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-slate-800/30 transition"
              >
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <span className="font-semibold text-sm text-slate-100">{tender.title}</span>
                    {tender.extraction_status === "READY" ? (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
                        READY
                      </span>
                    ) : tender.extraction_status === "REVIEW" ? (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-950 text-amber-400 border border-amber-800">
                        REVIEW MODE
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-950 text-blue-400 border border-blue-800">
                        {tender.extraction_status}
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
                    {tender.gem_tender_id && (
                      <span>
                        <strong className="text-slate-500">GeM:</strong> {tender.gem_tender_id}
                      </span>
                    )}
                    <span>
                      <strong className="text-slate-500">Pages:</strong> {tender.total_pages}
                    </span>
                    <span>
                      <strong className="text-slate-500">Extracted Clauses:</strong> {tender.clause_count || 0}
                    </span>
                    <span>
                      <strong className="text-slate-500">Uploaded:</strong>{" "}
                      {new Date(tender.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>

                <div className="flex items-center space-x-2">
                  <Link
                    href={`/tenders/${tender.id}/clauses`}
                    className="inline-flex items-center space-x-1.5 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium transition border border-slate-700"
                  >
                    <span>Review Requirements</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
