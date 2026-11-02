import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { NEEDS_REVIEW_ELIGIBILITY } from "../test/fixtures";
import { RequirementBreakdown } from "./RequirementBreakdown";

afterEach(cleanup);

describe("RequirementBreakdown", () => {
  it("shows the verdict, the API's summary and every requirement", () => {
    render(<RequirementBreakdown eligibility={NEEDS_REVIEW_ELIGIBILITY} />);
    expect(screen.getByText("Needs review")).toBeTruthy();
    expect(screen.getByText("One requirement could not be verified.")).toBeTruthy();
    expect(within(screen.getByRole("list", { name: "Requirement checks" })).getAllByRole("listitem")).toHaveLength(3);
  });

  it("labels AI-assisted results and prose-derived requirements, with their evidence", () => {
    render(<RequirementBreakdown eligibility={NEEDS_REVIEW_ELIGIBILITY} />);
    expect(screen.getByText("AI-assisted judgement")).toBeTruthy();
    expect(screen.getByText("Read from job description")).toBeTruthy();
    expect(screen.getByText(/Candidates must have no active backlogs/)).toBeTruthy();
    expect(screen.getByText(/flagged for review instead of ruling you out/)).toBeTruthy();
  });

  it("never shows a disqualifying verdict for a review-only result", () => {
    render(<RequirementBreakdown eligibility={NEEDS_REVIEW_ELIGIBILITY} />);
    expect(screen.queryByText("Not eligible")).toBeNull();
  });

  it("handles a job that states no structured requirements", () => {
    render(
      <RequirementBreakdown
        eligibility={{ ...NEEDS_REVIEW_ELIGIBILITY, eligibility_state: "ELIGIBLE", requirement_breakdown: [], summary: "No requirements stated." }}
      />,
    );
    expect(screen.getByText("Eligible")).toBeTruthy();
    expect(screen.getByText(/states no structured eligibility requirements/)).toBeTruthy();
  });
});
