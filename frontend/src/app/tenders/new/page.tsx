"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { uploadTenderPdf, triggerClauseExtraction } from "@/lib/api-client";
import { UploadCloud, FileText, CheckCircle2, AlertCircle, ArrowRight, Loader2 } from "lucide-react";

export default function NewTenderPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [gemTenderId, setGemTenderId] = useState("");
  const [step, setStep] = useState<"IDLE" | "UPLOADING" | "EXTRACTING" | "DONE">("IDLE");
  const [progressMsg, setProgressMsg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0];
      if (!selected.name.toLowerCase().endsWith(".pdf")) {
        setError("Please select a valid PDF file.");
        return;
      }
      setFile(selected);
      setError(null);
      if (!title) {
        setTitle(selected.name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " "));
      }
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const dropped = e.dataTransfer.files[0];
      if (!dropped.name.toLowerCase().endsWith(".pdf")) {
        setError("Please drop a valid PDF file.");
        return;
      }
      setFile(dropped);
      setError(null);
      if (!title) {
        setTitle(dropped.name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " "));
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError("Please select a Tender PDF file.");
      return;
    }
    if (!title.trim()) {
      setError("Please enter a Tender title.");
      return;
    }

    setError(null);
    try {
      // Step 1: Upload and parse pages with PyMuPDF
      setStep("UPLOADING");
      setProgressMsg("Uploading tender PDF and parsing page text with PyMuPDF...");
      const uploadedTender = await uploadTenderPdf(file, title.trim(), gemTenderId.trim() || undefined);

      // Step 2: Trigger AI clause extraction with NVIDIA NIM
      setStep("EXTRACTING");
      setProgressMsg(
        `Analyzing ${uploadedTender.total_pages} pages using NVIDIA NIM GPT-OSS 20B (3-page sliding windows with 1-page overlap)...`
      );
      await triggerClauseExtraction(uploadedTender.id);

      setStep("DONE");
      setProgressMsg("Clauses extracted successfully! Redirecting to Human Review...");
      setTimeout(() => {
        router.push(`/tenders/${uploadedTender.id}/clauses`);
      }, 1000);
    } catch (err: any) {
      setError(err.message || "Failed to process tender PDF.");
      setStep("IDLE");
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-slate-100">Upload GeM Tender Document</h2>
        <p className="text-sm text-slate-400 mt-1">
          Upload an official GeM Notice Inviting Tender (NIT) or RFP PDF. The platform will extract text using PyMuPDF and analyze compliance clauses using NVIDIA NIM GPT-OSS 20B.
        </p>
      </div>

      {error && (
        <div className="p-4 bg-rose-950/50 border border-rose-800 rounded-xl flex items-start space-x-3 text-rose-300 text-sm">
          <AlertCircle className="w-5 h-5 mt-0.5 text-rose-400 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {step !== "IDLE" ? (
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-8 text-center space-y-4">
          <div className="flex justify-center">
            {step === "DONE" ? (
              <CheckCircle2 className="w-12 h-12 text-emerald-400 animate-bounce" />
            ) : (
              <Loader2 className="w-12 h-12 text-blue-500 animate-spin" />
            )}
          </div>
          <h3 className="text-lg font-semibold text-slate-200">
            {step === "UPLOADING" && "Ingesting Tender Document"}
            {step === "EXTRACTING" && "AI Clause Extraction in Progress"}
            {step === "DONE" && "Extraction Complete!"}
          </h3>
          <p className="text-sm text-slate-400 max-w-md mx-auto">{progressMsg}</p>
          <div className="w-full bg-slate-800 rounded-full h-2 max-w-md mx-auto overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${
                step === "UPLOADING"
                  ? "w-1/3 bg-blue-500"
                  : step === "EXTRACTING"
                  ? "w-4/5 bg-indigo-500"
                  : "w-full bg-emerald-500"
              }`}
            />
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 space-y-4">
            {/* Title Input */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">
                Tender Title *
              </label>
              <input
                type="text"
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Procurement of Server Infrastructure and High-Performance Storage"
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 transition"
              />
            </div>

            {/* GeM Tender ID Input */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">
                GeM Bid / NIT Reference Number (Optional)
              </label>
              <input
                type="text"
                value={gemTenderId}
                onChange={(e) => setGemTenderId(e.target.value)}
                placeholder="e.g. GEM/2026/B/492104"
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 transition"
              />
            </div>

            {/* Drag and Drop Zone */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                Tender PDF File *
              </label>
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-slate-700 hover:border-blue-500 bg-slate-950/60 rounded-xl p-8 text-center cursor-pointer transition flex flex-col items-center justify-center space-y-3"
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf"
                  onChange={handleFileChange}
                  className="hidden"
                />
                <div className="h-12 w-12 rounded-full bg-blue-950/60 border border-blue-800/60 flex items-center justify-center text-blue-400">
                  <UploadCloud className="w-6 h-6" />
                </div>
                {file ? (
                  <div className="flex items-center space-x-2 text-sm text-emerald-400 font-medium">
                    <FileText className="w-4 h-4" />
                    <span>{file.name}</span>
                    <span className="text-slate-500 text-xs">
                      ({(file.size / (1024 * 1024)).toFixed(2)} MB)
                    </span>
                  </div>
                ) : (
                  <>
                    <p className="text-sm text-slate-300 font-medium">
                      Click to upload or drag & drop Tender PDF
                    </p>
                    <p className="text-xs text-slate-500">
                      Standard GeM NIT / Technical Specification document (PDF up to 50MB)
                    </p>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex justify-end space-x-3">
            <button
              type="button"
              onClick={() => router.push("/")}
              className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!file || !title.trim()}
              className="inline-flex items-center space-x-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition shadow-md shadow-blue-600/20 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span>Ingest & Extract Clauses</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
