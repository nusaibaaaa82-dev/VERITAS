export type VerdictType = 'TRUE' | 'FALSE' | 'PARTIALLY TRUE' | 'MISLEADING' | 'UNVERIFIED';

export interface VerdictItem {
  id: string;
  name: VerdictType;
  badge: string;
  tagline: string;
  description: string;
  criteria: string[];
  color: {
    primary: string;
    bg: string;
    border: string;
    glow?: string;
  };
}

export interface TechnologyItem {
  name: string;
  role: string;
  architecture: string;
  description: string;
  highlights: string[];
  tag: string;
}

export interface PipelineStep {
  step: string;
  title: string;
  description: string;
  detail: string;
}

// ============================================================================
// Backend API Schemas (Matching FastAPI backend/schemas/claim.py)
// ============================================================================

export interface HealthResponse {
  status: string;
}

export interface LanguageInfo {
  code: string;
  name: string;
  is_reliable: boolean;
  method: string;
  note?: string;
}

export interface ComparisonStatus {
  is_complete: boolean;
  models_evaluated: string[];
  status_message: string;
}

export interface ModelInferenceResult {
  model_name: string;
  is_available: boolean;
  prediction: string | null;
  status: string;
  details?: string;
  task?: string;
  repository?: string;
  classification_type?: string;
  architecture?: string;
  label_mapping?: Record<number, string>;
  language_support?: string;
  raw_class_id?: number;
  confidence?: number;
  inference_time_ms?: number;
  device?: string;
}

export interface EvidenceItem {
  id: string;
  title: string;
  publisher?: string;
  url?: string;
  published_date?: string;
  snippet: string;
  stance: string;
  is_verified: boolean;
  source_domain?: string;
  original_url?: string;
  canonical_url?: string;
  canonical_domain?: string;
  canonical_publisher?: string;
  source_tier?: string;
  source_type?: string;
  text_availability?: string;
  relevance_status?: string;
  relevance_score?: number;
  relevance_justification?: string;
  stance_justification?: string;
  duplicate_reason?: string;
  content_sha256?: string;
  is_potential_syndication?: boolean;
  syndication_notes?: string;
  doi?: string;
  is_full_text?: boolean;
  traceability?: Record<string, string>;
}

export interface VerdictAssessment {
  verdict: VerdictType;
  justification: string;
  evidence_count: number;
  independent_sources_count: number;
  has_sufficient_evidence: boolean;
  methodology_notes: string[];
}

export interface PropositionItem {
  id: string;
  claim_id: string;
  text: string;
  proposition_type: string;
  status: string;
  notes?: string;
}

export interface PropositionEvidenceMatch {
  proposition_id: string;
  proposition_text: string;
  evidence_id: string;
  evidence_title: string;
  relevance_status: string;
  relevance_score?: number;
  stance: string;
  explanation: string;
  source_url?: string;
  publisher?: string;
  source_tier: string;
  source_type: string;
  text_availability: string;
  is_verified: boolean;
}

export interface PropositionCoverage {
  proposition_id: string;
  proposition_text: string;
  proposition_type: string;
  coverage_status: string;
  supporting_count: number;
  contradicting_count: number;
  neutral_count: number;
  verified_supporting_count: number;
  verified_contradicting_count: number;
  unverified_supporting_count?: number;
  unverified_contradicting_count?: number;
  matches: PropositionEvidenceMatch[];
  notes?: string;
}

export interface ClaimDecompositionResult {
  claim_id: string;
  original_claim: string;
  status: string;
  propositions: PropositionItem[];
  proposition_coverage: PropositionCoverage[];
  total_propositions: number;
  verified_supported_count?: number;
  verified_contradicted_count?: number;
  unverified_supporting_count?: number;
  unverified_contradicting_count?: number;
  supported_propositions_count: number;
  contradicted_propositions_count: number;
  conflicting_propositions_count: number;
  unresolved_propositions_count: number;
  coverage_summary: string;
  decomposition_notes?: string;
}

export interface VerificationResultResponse {
  claim_id: string;
  claim: string;
  language: string;
  language_info: LanguageInfo;
  comparison_status: ComparisonStatus;
  models: Record<string, ModelInferenceResult>;
  evidence: EvidenceItem[];
  evidence_retrieval_status: string;
  decomposition?: ClaimDecompositionResult;
  verdict_assessment: VerdictAssessment;
  timestamp: string;
}

export interface ClaimReceiptResponse {
  success: boolean;
  message: string;
  claim: string;
  status: string;
}
