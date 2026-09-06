export interface SystemHealth {
  status: string;
  service: string;
  version: string;
  database: string;
  details?: {
    pgvector_extension?: {
      available: boolean;
      version?: string;
      note?: string;
    };
    db_error?: string;
  };
}

export interface NvidiaHealth {
  status: string;
  model: string;
  base_url: string;
  message: string;
  latency_ms?: number;
  response_sample?: string;
}

export interface TenderClause {
  id: string;
  tender_id: string;
  clause_code: string;
  category: "TECHNICAL" | "FINANCIAL" | "STATUTORY" | "EXPERIENCE" | "DELIVERY_SLA" | string;
  title: string;
  description: string;
  is_mandatory: boolean;
  rule_config?: Record<string, any> | null;
  source_text: string;
  page_number: number;
  is_confirmed: boolean;
  created_at: string;
  updated_at: string;
}

export interface Tender {
  id: string;
  title: string;
  gem_tender_id?: string | null;
  file_name?: string | null;
  total_pages: number;
  extraction_status: "UPLOADED" | "EXTRACTING" | "REVIEW" | "READY" | "FAILED" | string;
  created_at: string;
  updated_at: string;
  clause_count?: number;
  clauses?: TenderClause[];
}

export interface ClauseCreateInput {
  category: string;
  title: string;
  description: string;
  is_mandatory: boolean;
  rule_config?: Record<string, any> | null;
  source_text: string;
  page_number: number;
}

export interface ClauseUpdateInput {
  category?: string;
  title?: string;
  description?: string;
  is_mandatory?: boolean;
  rule_config?: Record<string, any> | null;
  source_text?: string;
  page_number?: number;
  is_confirmed?: boolean;
}
