// Mirrors of the backend's published Pydantic contracts. Field names and enum values are
// copied from app/schemas/*.py; nothing here is invented. When a backend schema changes,
// this file is the one place the UI has to follow.

// --- app/schemas/candidate.py ------------------------------------------------------------

export type GradeScale = "SCALE_4" | "SCALE_5" | "SCALE_10" | "PERCENTAGE" | "UNKNOWN";
export type DegreeLevel =
  | "HIGH_SCHOOL"
  | "DIPLOMA"
  | "BACHELORS"
  | "MASTERS"
  | "DOCTORATE"
  | "OTHER"
  | "UNKNOWN";
export type JobType = "INTERNSHIP" | "FULL_TIME" | "UNKNOWN";
/** A candidate may prefer only these; UNKNOWN is rejected by the API (ADR-029 D15). */
export type PreferableJobType = "INTERNSHIP" | "FULL_TIME";
export type WorkMode = "REMOTE" | "ONSITE" | "HYBRID" | "ANY";
export type Confidence = "HIGH" | "MEDIUM" | "LOW";

export interface EducationEntry {
  degree: string;
  level?: DegreeLevel;
  field_of_study?: string | null;
  institution?: string | null;
  grad_year?: number | null;
  cgpa?: number | null;
  scale?: GradeScale;
}

export interface ExperienceEntry {
  title: string;
  company?: string | null;
  duration?: string | null;
  description?: string | null;
}

export interface ProjectEntry {
  name: string;
  description?: string | null;
}

export interface CertificationEntry {
  name: string;
  issuer?: string | null;
  year?: number | null;
}

export interface CandidatePreferences {
  locations?: string[];
  job_types?: PreferableJobType[];
  work_mode?: WorkMode;
}

export interface CandidateProfile {
  candidate_id?: string | null;
  name?: string | null;
  email?: string | null;
  phone?: string | null;
  location?: string | null;
  education?: EducationEntry[];
  experience?: ExperienceEntry[];
  skills?: string[];
  projects?: ProjectEntry[];
  certifications?: CertificationEntry[];
  languages?: string[];
  /** null means not stated, which is NOT the same as zero (INV-3). */
  backlogs?: number | null;
  preferences?: CandidatePreferences;
  resume_raw_text?: string | null;
  field_confidence?: Record<string, Confidence>;
}

export type IssueSeverity = "ERROR" | "WARNING" | "INFO";

export interface ValidationIssue {
  field: string;
  code: string;
  message: string;
  severity: IssueSeverity;
}

export interface CandidateValidationResponse {
  candidate_id: string | null;
  is_valid: boolean;
  issues: ValidationIssue[];
  profile: CandidateProfile;
}

// --- app/schemas/job.py ------------------------------------------------------------------

export type JobStatus = "ACTIVE" | "EXPIRED" | "CLOSED" | "UNKNOWN";

export interface JobRead {
  id: string;
  company_name: string;
  role_title: string;
  job_type: JobType;
  location: string | null;
  description: string;
  requirements: Record<string, unknown>;
  min_cgpa: number | null;
  min_cgpa_scale: string | null;
  allowed_fields: string[];
  min_degree_level: DegreeLevel | null;
  max_backlogs: number | null;
  min_grad_year: number | null;
  max_grad_year: number | null;
  required_skills: string[];
  apply_link: string | null;
  deadline: string | null;
  source: string;
  source_job_id: string | null;
  status: JobStatus;
  is_active: boolean;
  last_verified_at: string;
}

export interface JobListResponse {
  items: JobRead[];
  total: number;
  limit: number;
  offset: number;
}

// --- app/schemas/eligibility.py ----------------------------------------------------------

export type EligibilityState =
  | "ELIGIBLE"
  | "LIKELY_ELIGIBLE"
  | "NEEDS_REVIEW"
  | "UNKNOWN"
  | "NOT_ELIGIBLE";
export type RequirementType =
  | "MIN_CGPA"
  | "GRAD_YEAR_WINDOW"
  | "MAX_BACKLOGS"
  | "MIN_DEGREE_LEVEL"
  | "ALLOWED_FIELDS";
export type RequirementStatus = "PASS" | "FAIL" | "UNKNOWN";
export type EvaluationMethod = "deterministic" | "ai_reasoning";
export type RequirementProvenance = "SOURCE_STATED" | "PROSE_DERIVED";

export interface RequirementResult {
  requirement_type: RequirementType;
  requirement: string;
  candidate_value: string | null;
  status: RequirementStatus;
  confidence: Confidence;
  method: EvaluationMethod;
  provenance: RequirementProvenance;
  reason_code: string;
  note: string;
  evidence: string | null;
}

export interface JobEligibility {
  job_id: string;
  company_name: string;
  role_title: string;
  job_status: JobStatus;
  apply_link: string | null;
  deadline: string | null;
  eligibility_state: EligibilityState;
  requirement_breakdown: RequirementResult[];
  summary: string;
}

// --- app/schemas/matching.py -------------------------------------------------------------

export type MatchScoreBasis =
  | "SCORED"
  | "NO_CANDIDATE_TERMS"
  | "NO_JOB_TERMS"
  | "WITHHELD_NOT_ELIGIBLE";

export interface SharedTerm {
  term: string;
  kind: "skill" | "text";
  contribution: number;
}

export interface RecommendationMatch {
  match_score: number | null;
  score_basis: MatchScoreBasis;
  matched_required_skills: string[];
  missing_required_skills: string[];
  required_skill_count: number;
  top_terms: SharedTerm[];
}

export interface RecommendationItem {
  rank: number | null;
  eligibility: JobEligibility;
  match: RecommendationMatch;
  explanation: string;
}

export interface RecommendationResponse {
  candidate_id: string | null;
  engine_version: string;
  matching_version: string;
  evaluated_at: string;
  corpus_size: number;
  corpus_fingerprint: string;
  jobs_considered: number;
  jobs_not_considered: number;
  ranked: RecommendationItem[];
  needs_review: RecommendationItem[];
  not_eligible: RecommendationItem[];
  not_open: RecommendationItem[];
  not_found_job_ids: string[];
}

/** The four recommendation groups, in the order the API documents them. */
export type RecommendationGroup = "ranked" | "needs_review" | "not_eligible" | "not_open";

// --- app/schemas/resume.py ---------------------------------------------------------------

export type ResumeParseStatus = "PARSED" | "PARTIAL" | "NEEDS_REVIEW";

export interface ResumeParseResponse {
  candidate_id: string | null;
  status: ResumeParseStatus;
  profile: CandidateProfile;
  field_confidence: Record<string, Confidence>;
  issues: ValidationIssue[];
  metadata: {
    source_format: "PDF" | "DOCX";
    characters_extracted: number;
    provider: string;
    model: string;
    duration_ms: number;
  };
}

// --- app/main.py -------------------------------------------------------------------------

export interface HealthResponse {
  status: string;
  version: string;
  environment: string;
}

export interface ErrorResponse {
  error: string;
  message: string;
  request_id: string;
  details: { field: string; code: string; message: string }[];
}
