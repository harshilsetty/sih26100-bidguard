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

export interface BidderDocument {
  id: string;
  bidder_id: string;
  file_name: string;
  doc_type?: string | null;
  total_pages: number;
  empty_pages_count: number;
  extraction_status: string;
  created_at: string;
}

export interface Bidder {
  id: string;
  tender_id: string;
  company_name: string;
  final_status: string;
  documents_count: number;
  chunks_count: number;
  evaluations_count: number;
  documents?: BidderDocument[];
  created_at: string;
  updated_at: string;
}

export interface BidderSummary {
  id: string;
  company_name: string;
  pass_count: number;
  fail_count: number;
  review_count: number;
  final_status: string;
  officer_recommendation?: string | null;
  has_contradiction?: boolean;
  officer_override_count?: number;
}

export interface ClauseSummary {
  id: string;
  clause_code: string;
  category: string;
  title: string;
  is_mandatory: boolean;
  rule_type?: string | null;
}

export interface EvaluationCellSummary {
  evaluation_id: string;
  bidder_id?: string;
  clause_id?: string;
  clause_code: string;
  status: "PASS" | "FAIL" | "REVIEW";
  original_status: "PASS" | "FAIL" | "REVIEW";
  confidence_score?: number | null;
  claimed_value?: string | null;
  reasoning?: string | null;
  contradiction_detected: boolean;
  evidence_page_number?: number | null;
  evidence_chunk_id?: string | null;
  document_name?: string | null;
  override_status?: "PASS" | "FAIL" | "REVIEW" | null;
  override_reason?: string | null;
}

export interface ComplianceMatrixResponse {
  tender_id: string;
  tender_title: string;
  gem_tender_id?: string;
  evaluation_date?: string;
  bidders: BidderSummary[];
  clauses: ClauseSummary[];
  matrix: Record<string, Record<string, EvaluationCellSummary>>;
  summary: {
    total_bidders: number;
    total_clauses: number;
    total_pass: number;
    total_fail: number;
    total_review: number;
    total_officer_overrides: number;
  };
}

export interface DeterministicRuleResult {
  rule_type: string;
  parameter?: string;
  required_value?: any;
  actual_value?: any;
  unit?: string;
  passed?: boolean | null;
  margin?: number | null;
  message: string;
}

export interface EvaluationDetailResponse {
  id?: string;
  evaluation_id?: string;
  tender_id: string;
  bidder_id: string;
  bidder_name: string;
  clause_id: string;
  clause_code: string;
  clause_title: string;
  clause_category: string;
  clause_source_text: string;
  clause_page_number: number;
  is_mandatory?: boolean;
  status: "PASS" | "FAIL" | "REVIEW";
  original_status: "PASS" | "FAIL" | "REVIEW";
  confidence_score?: number | null;
  claimed_value?: string | null;
  reasoning?: string | null;
  evidence_snippet?: string | null;
  evidence_page_number?: number | null;
  evidence_chunk_id?: string | null;
  document_name?: string | null;
  rule_result?: DeterministicRuleResult | null;
  contradiction_detected: boolean;
  contradiction_details?: string | null;
  override_status?: "PASS" | "FAIL" | "REVIEW" | null;
  override_reason?: string | null;
  overridden_by?: string | null;
  overridden_at?: string | null;
}

export interface OfficerOverrideRequest {
  override_status: "PASS" | "FAIL" | "REVIEW";
  override_reason: string;
  officer_id?: string;
}

export interface EvaluationRunRequest {
  use_live_llm?: boolean;
  bidder_ids?: string[];
}

export interface EvaluationRunResponse {
  tender_id: string;
  bidders_evaluated: number;
  total_evaluations: number;
  reports: any[];
}

export interface DemoBiddersLoadResponse {
  tender_id: string;
  message: string;
  bidders_count: number;
  bidders: Bidder[];
}

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export interface ScoreBreakdown {
  tender_compliance: number;
  statutory_consistency: number;
  evidence_completeness: number;
  contradiction_score: number;
}

export interface ScoreSummary {
  pass_count: number;
  fail_count: number;
  review_count: number;
  inconsistency_count: number;
  major_contradiction_count: number;
  minor_contradiction_count: number;
}

export interface BidderComplianceScore {
  bidder_id: string;
  tender_id?: string;
  company_name: string;
  overall_score: number;
  risk_level: RiskLevel;
  breakdown: ScoreBreakdown;
  risk_triggers: string[];
  summary: ScoreSummary;
  calculation_details?: Record<string, any>;
  disclaimer: string;
  created_at?: string;
}

export interface RankedBidderItem {
  rank: number;
  bidder_id: string;
  company_name: string;
  overall_score: number;
  risk_level: RiskLevel;
  breakdown: ScoreBreakdown;
  recommendation: string;
  warning_count: number;
  key_warnings: string[];
}

export interface TenderBidderRankingResponse {
  tender_id: string;
  tender_title: string;
  total_bidders: number;
  rankings: RankedBidderItem[];
  disclaimer: string;
  generated_at: string;
}

export type RecommendationCategory =
  | "RECOMMENDED_FOR_OFFICER_REVIEW"
  | "REQUIRES_ADDITIONAL_EVIDENCE"
  | "HIGH_RISK_OFFICER_REVIEW";

export type RecommendationSource = "AI" | "DETERMINISTIC_FALLBACK";

export type OfficerAction =
  | "ACKNOWLEDGED"
  | "NEEDS_ADDITIONAL_EVIDENCE"
  | "OVERRIDE_REVIEW"
  | "FINAL_OFFICER_DECISION";

export interface EvidenceReference {
  reference_id: string;
  clause_code?: string | null;
  source_type: string;
  source_name: string;
  page?: number | null;
  verification_id?: string | null;
  summary: string;
}

export interface AIRecommendationResponse {
  recommendation_id: string;
  tender_id: string;
  bidder_id: string;
  bidder_name: string;
  recommendation: RecommendationCategory;
  recommendation_source: RecommendationSource;
  confidence: string;
  overall_score: number;
  risk_level: string;
  executive_summary: string;
  key_reasons: string[];
  positive_findings: string[];
  risk_findings: string[];
  missing_evidence: string[];
  contradictions: string[];
  priority_actions: string[];
  supporting_references: EvidenceReference[];
  model_identifier: string;
  generated_at: string;
  disclaimer: string;
}

export interface OfficerReviewRequest {
  action: OfficerAction;
  justification: string;
  recommendation_id?: string | null;
}

export interface AuditRecordItem {
  id: string;
  tender_id: string;
  bidder_id: string;
  evaluation_id?: string | null;
  recommendation_id: string;
  event_type: string;
  recommendation_type: RecommendationCategory;
  recommendation_source: RecommendationSource;
  score_at_recommendation: number;
  risk_at_recommendation: string;
  recommendation_summary: string;
  key_reasons: string[];
  evidence_references: EvidenceReference[];
  positive_findings: string[];
  risk_findings: string[];
  priority_actions: string[];
  model_identifier: string;
  officer_action?: OfficerAction | null;
  officer_comment?: string | null;
  action_timestamp: string;
  disclaimer: string;
  created_at: string;
}

export interface AuditTrailResponse {
  tender_id: string;
  bidder_id: string;
  records: AuditRecordItem[];
}

