import { describe, expect, it } from "vitest";
import type { RequirementResult } from "../api/types";
import { VERDICTS, VERDICT_ORDER, reviewReason } from "./eligibility";

const base: RequirementResult = {
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
};

describe("verdict wording", () => {
  it("covers all five backend states, distinctly", () => {
    expect(VERDICT_ORDER).toEqual(["ELIGIBLE", "LIKELY_ELIGIBLE", "NEEDS_REVIEW", "UNKNOWN", "NOT_ELIGIBLE"]);
    const labels = VERDICT_ORDER.map((state) => VERDICTS[state].label);
    expect(new Set(labels).size).toBe(5);
    expect(VERDICTS.NOT_ELIGIBLE.tone).toBe("danger");
    expect(VERDICTS.NEEDS_REVIEW.tone).toBe("warning");
  });
});

describe("reviewReason", () => {
  it("is silent for a verified source-stated pass or fail", () => {
    expect(reviewReason(base)).toBeNull();
    expect(reviewReason({ ...base, status: "FAIL", reason_code: "BELOW_MINIMUM" })).toBeNull();
  });

  it("explains a prose-derived failure as a review item, never a disqualification", () => {
    const reason = reviewReason({ ...base, status: "FAIL", provenance: "PROSE_DERIVED", confidence: "MEDIUM" });
    expect(reason).toMatch(/flagged for review/);
    expect(reason).not.toMatch(/not eligible/i);
  });

  it("never presents an AI-assisted judgement as verified", () => {
    const reason = reviewReason({ ...base, method: "ai_reasoning", confidence: "MEDIUM", reason_code: "AI_FIELD_RELATED" });
    expect(reason).toMatch(/not verified by a rule/);
  });

  it("explains why an unknown result needs attention", () => {
    expect(reviewReason({ ...base, status: "UNKNOWN", reason_code: "MISSING_CANDIDATE_VALUE" })).toMatch(/Profile page/);
    expect(reviewReason({ ...base, status: "UNKNOWN", reason_code: "SCALE_MISMATCH" })).toMatch(/never converts/);
    expect(reviewReason({ ...base, status: "UNKNOWN", reason_code: "SOMETHING_NEW" })).toMatch(/could not be verified/);
  });

  it("says an inconclusive AI check verified nothing, rather than offering it as guidance", () => {
    const reason = reviewReason({
      ...base,
      status: "UNKNOWN",
      method: "ai_reasoning",
      confidence: "LOW",
      reason_code: "AI_ASSESSMENT_INCONCLUSIVE",
    });
    expect(reason).toMatch(/Nothing was verified/);
    expect(reason).not.toMatch(/guidance/);
  });
});
