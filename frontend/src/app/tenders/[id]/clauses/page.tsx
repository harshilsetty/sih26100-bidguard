"use client";

import { useEffect, useState, use } from "react";
import { useRouter } from "next/navigation";
import {
  fetchTenderDetail,
  updateClause,
  deleteClause,
  addManualClause,
  confirmTenderClauses,
} from "@/lib/api-client";
import { Tender, TenderClause, ClauseCreateInput } from "@/lib/types";
import {
  CheckCircle2,
  AlertCircle,
  FileText,
  Plus,
  Trash2,
  Edit2,
  Lock,
  Search,
  BookOpen,
  ArrowLeft,
  SlidersHorizontal,
  X,
} from "lucide-react";

export default function TenderClausesPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const resolvedParams = use(params);
  const tenderId = resolvedParams.id;
  const router = useRouter();

  const [tender, setTender] = useState<Tender | null>(null);
  const [clauses, setClauses] = useState<TenderClause[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Filters
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  // Modals & Panels
  const [evidenceModalClause, setEvidenceModalClause] = useState<TenderClause | null>(null);
  const [editModalClause, setEditModalClause] = useState<TenderClause | null>(null);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);

  // New Clause Form State
  const [newCategory, setNewCategory] = useState("TECHNICAL");
  const [newTitle, setNewTitle] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newMandatory, setNewMandatory] = useState(true);
  const [newSourceText, setNewSourceText] = useState("");
  const [newPageNum, setNewPageNum] = useState(1);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchTenderDetail(tenderId);
      setTender(data);
      setClauses(data.clauses || []);
    } catch (err: any) {
      setError(err.message || "Failed to load tender requirements");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [tenderId]);

  const handleToggleMandatory = async (clause: TenderClause) => {
    try {
      const updated = await updateClause(tenderId, clause.id, {
        is_mandatory: !clause.is_mandatory,
      });
      setClauses((prev) => prev.map((c) => (c.id === clause.id ? updated : c)));
    } catch (err: any) {
      setError(err.message || "Failed to update clause");
    }
  };

  const handleDeleteClause = async (clauseId: string) => {
    if (!confirm("Are you sure you want to remove this requirement?")) return;
    try {
      await deleteClause(tenderId, clauseId);
      setClauses((prev) => prev.filter((c) => c.id !== clauseId));
    } catch (err: any) {
      setError(err.message || "Failed to delete clause");
    }
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editModalClause) return;
    try {
      const updated = await updateClause(tenderId, editModalClause.id, {
        title: editModalClause.title,
        description: editModalClause.description,
        is_mandatory: editModalClause.is_mandatory,
        category: editModalClause.category,
        page_number: editModalClause.page_number,
        source_text: editModalClause.source_text,
      });
      setClauses((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
      setEditModalClause(null);
      setSuccessMsg("Clause updated successfully.");
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err: any) {
      setError(err.message || "Failed to save edit");
    }
  };

  const handleAddClause = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const input: ClauseCreateInput = {
        category: newCategory,
        title: newTitle.trim(),
        description: newDesc.trim(),
        is_mandatory: newMandatory,
        source_text: newSourceText.trim() || "Manually specified by procurement officer",
        page_number: newPageNum,
      };
      const created = await addManualClause(tenderId, input);
      setClauses((prev) => [...prev, created]);
      setIsAddModalOpen(false);
      // Reset form
      setNewTitle("");
      setNewDesc("");
      setNewSourceText("");
      setSuccessMsg("Custom requirement added.");
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err: any) {
      setError(err.message || "Failed to add requirement");
    }
  };

  const handleConfirmAll = async () => {
    if (
      !confirm(
        "Confirm and lock these requirements? Once confirmed, this tender will be marked READY for bidder compliance evaluations."
      )
    ) {
      return;
    }

    try {
      const updatedTender = await confirmTenderClauses(tenderId);
      setTender(updatedTender);
      setClauses(updatedTender.clauses || []);
      setSuccessMsg(
        "Tender requirements locked and confirmed! Status is now READY for Bidder Proposals."
      );
    } catch (err: any) {
      setError(err.message || "Failed to confirm requirements");
    }
  };

  // Categories count
  const categories = [
    { id: "ALL", label: "All Requirements", count: clauses.length },
    { id: "TECHNICAL", label: "Technical", count: clauses.filter((c) => c.category === "TECHNICAL").length },
    { id: "FINANCIAL", label: "Financial", count: clauses.filter((c) => c.category === "FINANCIAL").length },
    { id: "STATUTORY", label: "Statutory & GeM", count: clauses.filter((c) => c.category === "STATUTORY").length },
    { id: "EXPERIENCE", label: "Experience", count: clauses.filter((c) => c.category === "EXPERIENCE").length },
    { id: "DELIVERY_SLA", label: "Delivery & SLA", count: clauses.filter((c) => c.category === "DELIVERY_SLA").length },
  ];

  const filteredClauses = clauses.filter((c) => {
    const matchesCategory = selectedCategory === "ALL" || c.category === selectedCategory;
    const matchesQuery =
      searchQuery === "" ||
      c.clause_code.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.description.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesQuery;
  });

  if (loading) {
    return (
      <div className="py-20 text-center space-y-3">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-blue-500 border-t-transparent"></div>
        <p className="text-sm text-slate-400">Loading tender requirements and evidence provenance...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header Info */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 shadow-sm">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-1">
            <button
              onClick={() => router.push("/")}
              className="inline-flex items-center text-xs text-slate-400 hover:text-slate-200 transition mb-2"
            >
              <ArrowLeft className="w-3.5 h-3.5 mr-1" /> Back to Dashboard
            </button>
            <div className="flex items-center space-x-3">
              <h2 className="text-xl font-bold text-slate-100">{tender?.title}</h2>
              {tender?.extraction_status === "READY" ? (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
                  <CheckCircle2 className="w-3 h-3 mr-1" /> READY
                </span>
              ) : (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-950 text-amber-400 border border-amber-800">
                  <SlidersHorizontal className="w-3 h-3 mr-1" /> REVIEW MODE
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400 pt-1">
              {tender?.gem_tender_id && (
                <span>
                  <strong className="text-slate-300">GeM Ref:</strong> {tender.gem_tender_id}
                </span>
              )}
              <span>
                <strong className="text-slate-300">Total Pages:</strong> {tender?.total_pages}
              </span>
              <span>
                <strong className="text-slate-300">Extracted Requirements:</strong> {clauses.length}
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={() => setIsAddModalOpen(true)}
              className="inline-flex items-center space-x-1.5 px-3.5 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 rounded-lg text-xs font-medium transition"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add Custom Requirement</span>
            </button>
            <button
              onClick={handleConfirmAll}
              className="inline-flex items-center space-x-2 px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-medium transition shadow-sm"
            >
              <Lock className="w-3.5 h-3.5" />
              <span>Confirm & Lock Requirements</span>
            </button>
          </div>
        </div>
      </div>

      {successMsg && (
        <div className="p-4 bg-emerald-950/60 border border-emerald-800 rounded-xl flex items-center space-x-3 text-emerald-300 text-sm">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {error && (
        <div className="p-4 bg-rose-950/60 border border-rose-800 rounded-xl flex items-center space-x-3 text-rose-300 text-sm">
          <AlertCircle className="w-5 h-5 text-rose-400 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Category Tabs & Search Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Category Pills */}
        <div className="flex flex-wrap gap-2">
          {categories.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition flex items-center space-x-2 ${
                selectedCategory === cat.id
                  ? "bg-blue-600 text-white shadow-sm"
                  : "bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200"
              }`}
            >
              <span>{cat.label}</span>
              <span
                className={`px-1.5 py-0.2 rounded text-[10px] ${
                  selectedCategory === cat.id
                    ? "bg-blue-700 text-white"
                    : "bg-slate-800 text-slate-400"
                }`}
              >
                {cat.count}
              </span>
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative w-full md:w-64">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search requirements..."
            className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
        </div>
      </div>

      {/* Clauses Table */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-950/80 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
              <tr>
                <th className="px-4 py-3 w-28">Code</th>
                <th className="px-4 py-3 w-32">Category</th>
                <th className="px-4 py-3">Requirement & Specifications</th>
                <th className="px-4 py-3 w-28 text-center">Mandatory</th>
                <th className="px-4 py-3 w-32">Evidence</th>
                <th className="px-4 py-3 w-24 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {filteredClauses.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-slate-500">
                    No requirements found for the selected filter.
                  </td>
                </tr>
              ) : (
                filteredClauses.map((clause) => (
                  <tr key={clause.id} className="hover:bg-slate-800/40 transition">
                    <td className="px-4 py-3 font-mono font-semibold text-blue-400">
                      {clause.clause_code}
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
                        {clause.category}
                      </span>
                    </td>
                    <td className="px-4 py-3 space-y-1">
                      <p className="font-semibold text-slate-100">{clause.title}</p>
                      <p className="text-slate-400 line-clamp-2">{clause.description}</p>
                      {clause.rule_config && (
                        <div className="pt-1">
                          <span className="inline-block px-2 py-0.5 rounded text-[10px] font-mono bg-blue-950/60 text-blue-300 border border-blue-800/50">
                            Rule: {JSON.stringify(clause.rule_config)}
                          </span>
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        onClick={() => handleToggleMandatory(clause)}
                        className={`px-2.5 py-1 rounded-full text-[10px] font-semibold transition ${
                          clause.is_mandatory
                            ? "bg-rose-950/80 text-rose-300 border border-rose-800/80 hover:bg-rose-900"
                            : "bg-slate-800 text-slate-400 border border-slate-700 hover:bg-slate-700"
                        }`}
                      >
                        {clause.is_mandatory ? "MANDATORY" : "OPTIONAL"}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setEvidenceModalClause(clause)}
                        className="inline-flex items-center space-x-1 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-[11px] transition"
                      >
                        <BookOpen className="w-3 h-3 text-blue-400" />
                        <span>Page {clause.page_number}</span>
                      </button>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end space-x-2">
                        <button
                          onClick={() => setEditModalClause({ ...clause })}
                          className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
                          title="Edit Requirement"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleDeleteClause(clause.id)}
                          className="p-1 rounded hover:bg-rose-950/60 text-slate-400 hover:text-rose-400 transition"
                          title="Delete Requirement"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Evidence Provenance Modal */}
      {evidenceModalClause && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-2">
                <FileText className="w-4 h-4 text-blue-400" />
                <h3 className="font-semibold text-sm text-slate-100">
                  Verbatim Source Evidence Provenance
                </h3>
              </div>
              <button
                onClick={() => setEvidenceModalClause(null)}
                className="text-slate-400 hover:text-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div className="flex justify-between text-slate-400">
                <span>Clause Code: <strong className="text-blue-400 font-mono">{evidenceModalClause.clause_code}</strong></span>
                <span>Page in Tender: <strong className="text-slate-200">Page {evidenceModalClause.page_number}</strong></span>
              </div>
              <div>
                <p className="text-slate-400 font-medium mb-1">Requirement Title:</p>
                <p className="text-slate-100 font-semibold">{evidenceModalClause.title}</p>
              </div>
              <div>
                <p className="text-slate-400 font-medium mb-1">Ground Truth Snippet from Document:</p>
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-slate-300 font-serif leading-relaxed italic">
                  "{evidenceModalClause.source_text}"
                </div>
              </div>
            </div>
            <div className="flex justify-end pt-2">
              <button
                onClick={() => setEvidenceModalClause(null)}
                className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Clause Modal */}
      {editModalClause && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4 backdrop-blur-sm">
          <form
            onSubmit={handleSaveEdit}
            className="bg-slate-900 border border-slate-800 rounded-xl max-w-xl w-full p-6 space-y-4 shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-semibold text-sm text-slate-100">
                Edit Requirement ({editModalClause.clause_code})
              </h3>
              <button
                type="button"
                onClick={() => setEditModalClause(null)}
                className="text-slate-400 hover:text-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-400 font-medium mb-1">Category</label>
                <select
                  value={editModalClause.category}
                  onChange={(e) =>
                    setEditModalClause({ ...editModalClause, category: e.target.value })
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100"
                >
                  <option value="TECHNICAL">TECHNICAL</option>
                  <option value="FINANCIAL">FINANCIAL</option>
                  <option value="STATUTORY">STATUTORY</option>
                  <option value="EXPERIENCE">EXPERIENCE</option>
                  <option value="DELIVERY_SLA">DELIVERY_SLA</option>
                </select>
              </div>
              <div>
                <label className="block text-slate-400 font-medium mb-1">Title</label>
                <input
                  type="text"
                  required
                  value={editModalClause.title}
                  onChange={(e) =>
                    setEditModalClause({ ...editModalClause, title: e.target.value })
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100"
                />
              </div>
              <div>
                <label className="block text-slate-400 font-medium mb-1">Description</label>
                <textarea
                  rows={3}
                  required
                  value={editModalClause.description}
                  onChange={(e) =>
                    setEditModalClause({ ...editModalClause, description: e.target.value })
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100"
                />
              </div>
              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="editMandatory"
                  checked={editModalClause.is_mandatory}
                  onChange={(e) =>
                    setEditModalClause({
                      ...editModalClause,
                      is_mandatory: e.target.checked,
                    })
                  }
                  className="rounded border-slate-700 text-blue-600 focus:ring-0"
                />
                <label htmlFor="editMandatory" className="text-slate-300 font-medium cursor-pointer">
                  Mandatory criteria (Non-compliance disqualifies bid)
                </label>
              </div>
            </div>
            <div className="flex justify-end space-x-2 pt-2">
              <button
                type="button"
                onClick={() => setEditModalClause(null)}
                className="px-4 py-1.5 bg-slate-800 text-slate-300 rounded-lg text-xs"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-medium"
              >
                Save Changes
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Add Custom Requirement Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4 backdrop-blur-sm">
          <form
            onSubmit={handleAddClause}
            className="bg-slate-900 border border-slate-800 rounded-xl max-w-xl w-full p-6 space-y-4 shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-semibold text-sm text-slate-100">
                Add Custom Tender Requirement
              </h3>
              <button
                type="button"
                onClick={() => setIsAddModalOpen(false)}
                className="text-slate-400 hover:text-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 font-medium mb-1">Category</label>
                  <select
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100"
                  >
                    <option value="TECHNICAL">TECHNICAL</option>
                    <option value="FINANCIAL">FINANCIAL</option>
                    <option value="STATUTORY">STATUTORY</option>
                    <option value="EXPERIENCE">EXPERIENCE</option>
                    <option value="DELIVERY_SLA">DELIVERY_SLA</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-400 font-medium mb-1">Source Page</label>
                  <input
                    type="number"
                    min={1}
                    value={newPageNum}
                    onChange={(e) => setNewPageNum(parseInt(e.target.value) || 1)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100"
                  />
                </div>
              </div>
              <div>
                <label className="block text-slate-400 font-medium mb-1">Requirement Title *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. OEM Authorized Partner Certification"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100"
                />
              </div>
              <div>
                <label className="block text-slate-400 font-medium mb-1">Description *</label>
                <textarea
                  rows={3}
                  required
                  placeholder="Detailed criteria for evaluation..."
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100"
                />
              </div>
              <div>
                <label className="block text-slate-400 font-medium mb-1">Source Quote from PDF (Optional)</label>
                <textarea
                  rows={2}
                  placeholder="Verbatim text reference..."
                  value={newSourceText}
                  onChange={(e) => setNewSourceText(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100"
                />
              </div>
              <div className="flex items-center space-x-2 pt-1">
                <input
                  type="checkbox"
                  id="newMandatory"
                  checked={newMandatory}
                  onChange={(e) => setNewMandatory(e.target.checked)}
                  className="rounded border-slate-700 text-blue-600 focus:ring-0"
                />
                <label htmlFor="newMandatory" className="text-slate-300 font-medium cursor-pointer">
                  Mandatory criteria (Disqualifies bid if not satisfied)
                </label>
              </div>
            </div>
            <div className="flex justify-end space-x-2 pt-2">
              <button
                type="button"
                onClick={() => setIsAddModalOpen(false)}
                className="px-4 py-1.5 bg-slate-800 text-slate-300 rounded-lg text-xs"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-medium"
              >
                Add Requirement
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
