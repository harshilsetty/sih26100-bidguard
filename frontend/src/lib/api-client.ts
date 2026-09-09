import {
  SystemHealth,
  NvidiaHealth,
  Tender,
  TenderClause,
  ClauseCreateInput,
  ClauseUpdateInput,
  Bidder,
  DemoBiddersLoadResponse,
  ComplianceMatrixResponse,
  EvaluationDetailResponse,
  OfficerOverrideRequest,
  EvaluationRunRequest,
  EvaluationRunResponse,
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchSystemHealth(): Promise<SystemHealth> {
  const response = await fetch(`${API_BASE_URL}/api/v1/health`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Health check failed with status: ${response.status}`);
  }
  return response.json();
}

export async function fetchNvidiaHealth(): Promise<NvidiaHealth> {
  const response = await fetch(`${API_BASE_URL}/api/v1/health/nvidia`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`NVIDIA health check failed with status: ${response.status}`);
  }
  return response.json();
}

export async function uploadTenderPdf(
  file: File,
  title: string,
  gemTenderId?: string
): Promise<Tender> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("title", title);
  if (gemTenderId) {
    formData.append("gem_tender_id", gemTenderId);
  }

  const response = await fetch(`${API_BASE_URL}/api/v1/tenders/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed with status ${response.status}`);
  }

  return response.json();
}

export async function triggerClauseExtraction(tenderId: string): Promise<{
  tender_id: string;
  extraction_status: string;
  total_pages: number;
  extracted_count: number;
  clauses: TenderClause[];
}> {
  const response = await fetch(`${API_BASE_URL}/api/v1/tenders/${tenderId}/extract`, {
    method: "POST",
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Extraction failed with status ${response.status}`);
  }

  return response.json();
}

export async function fetchTenders(): Promise<Tender[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/tenders`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch tenders: ${response.status}`);
  }
  return response.json();
}

export async function fetchTenderDetail(tenderId: string): Promise<Tender> {
  const response = await fetch(`${API_BASE_URL}/api/v1/tenders/${tenderId}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch tender detail: ${response.status}`);
  }
  return response.json();
}

export async function fetchTenderClauses(tenderId: string): Promise<TenderClause[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/tenders/${tenderId}/clauses`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch clauses: ${response.status}`);
  }
  return response.json();
}

export async function addManualClause(
  tenderId: string,
  clause: ClauseCreateInput
): Promise<TenderClause> {
  const response = await fetch(`${API_BASE_URL}/api/v1/tenders/${tenderId}/clauses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(clause),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to add clause: ${response.status}`);
  }

  return response.json();
}

export async function updateClause(
  tenderId: string,
  clauseId: string,
  updates: ClauseUpdateInput
): Promise<TenderClause> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/tenders/${tenderId}/clauses/${clauseId}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    }
  );

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to update clause: ${response.status}`);
  }

  return response.json();
}

export async function deleteClause(
  tenderId: string,
  clauseId: string
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/tenders/${tenderId}/clauses/${clauseId}`,
    {
      method: "DELETE",
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to delete clause: ${response.status}`);
  }
}

export async function confirmTenderClauses(tenderId: string): Promise<Tender> {
  const response = await fetch(`${API_BASE_URL}/api/v1/tenders/${tenderId}/confirm`, {
    method: "POST",
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to confirm clauses: ${response.status}`);
  }

  return response.json();
}

export async function fetchTenderBidders(tenderId: string): Promise<Bidder[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/tenders/${tenderId}/bidders`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch bidders: ${response.status}`);
  }
  return response.json();
}

export async function createBidder(
  tenderId: string,
  companyName: string,
  files?: File[]
): Promise<Bidder> {
  const formData = new FormData();
  formData.append("company_name", companyName);
  if (files && files.length > 0) {
    for (const f of files) {
      formData.append("files", f);
    }
  }

  const response = await fetch(`${API_BASE_URL}/api/v1/tenders/${tenderId}/bidders`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to create bidder: ${response.status}`);
  }

  return response.json();
}

export async function loadDemoBidders(tenderId: string): Promise<DemoBiddersLoadResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/tenders/${tenderId}/bidders/demo`, {
    method: "POST",
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to load demo bidders: ${response.status}`);
  }

  return response.json();
}

export async function deleteBidder(tenderId: string, bidderId: string): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/tenders/${tenderId}/bidders/${bidderId}`,
    {
      method: "DELETE",
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to delete bidder: ${response.status}`);
  }
}

export async function triggerComplianceEvaluation(
  tenderId: string,
  options?: EvaluationRunRequest
): Promise<EvaluationRunResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/tenders/${tenderId}/evaluations/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options || { use_live_llm: false }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Evaluation run failed with status: ${response.status}`);
  }

  return response.json();
}

export async function fetchComplianceMatrix(tenderId: string): Promise<ComplianceMatrixResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/tenders/${tenderId}/evaluations/matrix`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch compliance matrix: ${response.status}`);
  }

  return response.json();
}

export async function fetchEvaluationDetail(
  tenderId: string,
  evaluationId: string
): Promise<EvaluationDetailResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/tenders/${tenderId}/evaluations/${evaluationId}`,
    {
      cache: "no-store",
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch evaluation detail: ${response.status}`);
  }

  return response.json();
}

export async function submitOfficerOverride(
  tenderId: string,
  evaluationId: string,
  req: OfficerOverrideRequest
): Promise<EvaluationDetailResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/tenders/${tenderId}/evaluations/${evaluationId}/override`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }
  );

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to submit officer override: ${response.status}`);
  }

  return response.json();
}

