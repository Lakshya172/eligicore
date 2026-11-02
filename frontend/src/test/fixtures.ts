// Synthetic fixtures for UI tests, shaped exactly like the API's responses.
import type { JobEligibility, JobRead, RecommendationItem, RecommendationResponse } from "../api/types";

export const JOB: JobRead = {
  id: "job-1",
  company_name: "Example Analytics Pvt. Ltd.",
  role_title: "Software Engineering Intern",
  job_type: "INTERNSHIP",
  location: "Bengaluru, India",
  description: "Six-month internship building internal data tooling.",
  requirements: { notes: "Open to pre-final and final year students." },
  min_cgpa: 7,
  min_cgpa_scale: "SCALE_10",
  allowed_fields: ["Computer Science", "Information Technology"],
  min_degree_level: null,
  max_backlogs: 0,
  min_grad_year: 2026,
  max_grad_year: 2027,
  required_skills: ["Python", "SQL"],
  apply_link: "https://careers.example.com/roles/swe-intern-2027",
  deadline: "2026-11-15",
  source: "curated",
  source_job_id: "EX-INT-001",
  status: "ACTIVE",
  is_active: true,
  last_verified_at: "2026-11-01T10:00:00Z",
};

export const JOB_2: JobRead = {
  ...JOB,
  id: "job-2",
  company_name: "Sample Systems Ltd.",
  role_title: "Backend Engineer",
  job_type: "FULL_TIME",
  location: "Remote, India",
  source_job_id: "EX-FT-002",
};

export const NEEDS_REVIEW_ELIGIBILITY: JobEligibility = {
  job_id: "job-1",
  company_name: JOB.company_name,
  role_title: JOB.role_title,
  job_status: "ACTIVE",
  apply_link: JOB.apply_link,
  deadline: JOB.deadline,
  eligibility_state: "NEEDS_REVIEW",
  summary: "One requirement could not be verified.",
  requirement_breakdown: [
    {
      requirement_type: "MIN_CGPA",
      requirement: "Minimum CGPA 7.0 (SCALE_10)",
      candidate_value: "8.2 (SCALE_10)",
      status: "PASS",
      confidence: "HIGH",
      method: "deterministic",
      provenance: "SOURCE_STATED",
      reason_code: "MEETS_MINIMUM",
      note: "8.2 meets the minimum of 7.0.",
      evidence: null,
    },
    {
      requirement_type: "ALLOWED_FIELDS",
      requirement: "Field of study in: Computer Science",
      candidate_value: "Data Science",
      status: "UNKNOWN",
      confidence: "LOW",
      method: "ai_reasoning",
      provenance: "SOURCE_STATED",
      reason_code: "AI_ASSESSMENT_INCONCLUSIVE",
      note: "The field could not be confirmed as related.",
      evidence: null,
    },
    {
      requirement_type: "MAX_BACKLOGS",
      requirement: "At most 0 active backlogs",
      candidate_value: "1",
      status: "FAIL",
      confidence: "MEDIUM",
      method: "deterministic",
      provenance: "PROSE_DERIVED",
      reason_code: "EXCEEDS_LIMIT",
      note: "1 exceeds the limit of 0.",
      evidence: "Candidates must have no active backlogs.",
    },
  ],
};

export function recommendationItem(eligibility: JobEligibility): RecommendationItem {
  return {
    rank: 1,
    eligibility,
    match: {
      match_score: 42.5,
      score_basis: "SCORED",
      matched_required_skills: ["Python"],
      missing_required_skills: ["SQL"],
      required_skill_count: 2,
      top_terms: [],
    },
    explanation: eligibility.summary,
  };
}

export function recommendationResponse(partial: Partial<RecommendationResponse>): RecommendationResponse {
  return {
    candidate_id: null,
    engine_version: "3",
    matching_version: "1",
    evaluated_at: "2026-11-02T10:00:00Z",
    corpus_size: 2,
    corpus_fingerprint: "test",
    jobs_considered: 2,
    jobs_not_considered: 0,
    ranked: [],
    needs_review: [],
    not_eligible: [],
    not_open: [],
    not_found_job_ids: [],
    ...partial,
  };
}
