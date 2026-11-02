// How eligibility results are worded in the UI. The verdicts, statuses and reason codes are
// the backend's (app/schemas/eligibility.py); this module only explains them in plain
// language and never changes or upgrades one.

import type {
  Confidence,
  EligibilityState,
  EvaluationMethod,
  RequirementProvenance,
  RequirementResult,
  RequirementStatus,
} from "../api/types";

export type Tone = "success" | "info" | "warning" | "neutral" | "danger";

export interface VerdictMeta {
  label: string;
  tone: Tone;
  /** One sentence on what this verdict means — and what it does not. */
  meaning: string;
}

export const VERDICTS: Record<EligibilityState, VerdictMeta> = {
  ELIGIBLE: {
    label: "Eligible",
    tone: "success",
    meaning:
      "Every requirement this job states in a structured field was checked against your profile and passed.",
  },
  LIKELY_ELIGIBLE: {
    label: "Likely eligible",
    tone: "info",
    meaning:
      "Every requirement passed, but at least one result relied on an AI-assisted judgement or on a requirement read from the job description, so it is not fully verified.",
  },
  NEEDS_REVIEW: {
    label: "Needs review",
    tone: "warning",
    meaning:
      "At least one requirement could not be verified. Check the flagged items yourself before applying.",
  },
  UNKNOWN: {
    label: "Unknown",
    tone: "neutral",
    meaning:
      "Nothing could be verified, usually because your profile is missing the values this job asks about.",
  },
  NOT_ELIGIBLE: {
    label: "Not eligible",
    tone: "danger",
    meaning:
      "A requirement the employer states in a structured field was checked and failed. That result is final and AI cannot override it.",
  },
};

/** Display order: the best outcome first, matching the recommendation groups. */
export const VERDICT_ORDER: EligibilityState[] = [
  "ELIGIBLE",
  "LIKELY_ELIGIBLE",
  "NEEDS_REVIEW",
  "UNKNOWN",
  "NOT_ELIGIBLE",
];

export const REQUIREMENT_STATUS: Record<RequirementStatus, { label: string; tone: Tone }> = {
  PASS: { label: "Pass", tone: "success" },
  FAIL: { label: "Fail", tone: "danger" },
  UNKNOWN: { label: "Not verified", tone: "neutral" },
};

export const METHOD_LABEL: Record<EvaluationMethod, string> = {
  deterministic: "Rule check",
  ai_reasoning: "AI-assisted judgement",
};

export const PROVENANCE_LABEL: Record<RequirementProvenance, string> = {
  SOURCE_STATED: "Stated by employer",
  PROSE_DERIVED: "Read from job description",
};

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  HIGH: "High confidence",
  MEDIUM: "Medium confidence",
  LOW: "Low confidence",
};

/**
 * Why a requirement still needs the student's attention, or null when it does not.
 *
 * The order matters: a prose-derived failure is explained as a review item, never as a
 * disqualification, because only a SOURCE_STATED deterministic FAIL can make a job
 * NOT_ELIGIBLE (ADR-030 D2, D4).
 */
export function reviewReason(result: RequirementResult): string | null {
  if (result.provenance === "PROSE_DERIVED" && result.status === "FAIL") {
    return "This requirement was read from the job description rather than a structured field, so a failed check is flagged for review instead of ruling you out. Confirm the wording with the employer.";
  }
  if (result.method === "ai_reasoning" && result.status !== "UNKNOWN") {
    return "This was judged by an AI-assisted check, not verified by a rule. Treat it as guidance and confirm it with the employer.";
  }
  if (result.status !== "UNKNOWN") {
    return null;
  }
  switch (result.reason_code) {
    case "MISSING_CANDIDATE_VALUE":
      return "Your profile does not include this value yet. Add it on the Profile page to have it checked.";
    case "CANDIDATE_SCALE_UNKNOWN":
      return "Your grade has no grading scale, so it cannot be compared. Select the scale on the Profile page.";
    case "SCALE_MISMATCH":
      return "Your grade and the job's cutoff use different grading scales. EligiCore never converts between scales, so check this one yourself.";
    case "FIELD_NOT_EXACT_MATCH":
      return "Your field of study is not an exact match for a permitted field, and it could not be confirmed as related.";
    case "SKIPPED_AFTER_HARD_FAILURE":
      return "Not checked because another stated requirement already failed.";
    case "JOB_SCALE_MISSING":
    case "JOB_SCALE_INVALID":
    case "JOB_VALUE_EXCEEDS_SCALE":
    case "INVALID_JOB_REQUIREMENT":
      return "The posting states this requirement in a way that cannot be checked reliably.";
    case "AI_ASSESSMENT_UNAVAILABLE":
    case "AI_ASSESSMENT_INCONCLUSIVE":
    case "AI_FIELD_NOT_RELATED":
      return "Your field of study is not an exact match, and an AI-assisted check could not confirm it as related. Nothing was verified either way — check with the employer.";
    default:
      return "This requirement could not be verified with the information available.";
  }
}
