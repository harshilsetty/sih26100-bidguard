import {
  SystemHealth,
  NvidiaHealth,
  Tender,
  TenderClause,
  ClauseCreateInput,
  ClauseUpdateInput,
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
