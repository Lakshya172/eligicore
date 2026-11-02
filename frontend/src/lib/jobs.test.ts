import { describe, expect, it } from "vitest";
import { JOB } from "../test/fixtures";
import { employerNotes, matchesSearch, safeExternalUrl, statedRequirements } from "./jobs";

describe("matchesSearch", () => {
  it("matches every term across title, company, location and skills", () => {
    expect(matchesSearch(JOB, "")).toBe(true);
    expect(matchesSearch(JOB, "intern bengaluru")).toBe(true);
    expect(matchesSearch(JOB, "SQL analytics")).toBe(true);
    expect(matchesSearch(JOB, "intern london")).toBe(false);
  });
});

describe("statedRequirements", () => {
  it("lists only what the job states in structured fields", () => {
    expect(statedRequirements(JOB)).toEqual([
      { label: "Minimum grade", value: "7 out of 10" },
      { label: "Graduation year", value: "2026 – 2027" },
      { label: "Backlogs", value: "None allowed" },
      { label: "Fields of study", value: "Computer Science, Information Technology" },
    ]);
  });

  it("says when a grade cutoff has no stated scale instead of assuming one", () => {
    const [grade] = statedRequirements({ ...JOB, min_cgpa_scale: null });
    expect(grade!.value).toBe("7 scale not stated");
  });

  it("returns nothing for a job with no structured requirements", () => {
    expect(
      statedRequirements({
        ...JOB,
        min_cgpa: null,
        min_grad_year: null,
        max_grad_year: null,
        max_backlogs: null,
        allowed_fields: [],
      }),
    ).toEqual([]);
  });
});

describe("display helpers", () => {
  it("reads free-text employer notes", () => {
    expect(employerNotes(JOB)).toMatch(/pre-final/);
    expect(employerNotes({ ...JOB, requirements: {} })).toBeNull();
  });

  it("renders only http(s) links", () => {
    expect(safeExternalUrl(JOB.apply_link)).toBe(JOB.apply_link);
    expect(safeExternalUrl("javascript:alert(1)")).toBeNull();
    expect(safeExternalUrl("not a url")).toBeNull();
    expect(safeExternalUrl(null)).toBeNull();
  });
});
