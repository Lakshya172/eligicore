import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { EligibilityState } from "../api/types";
import { VERDICTS, VERDICT_ORDER } from "../lib/eligibility";
import { Landing } from "../pages/Landing";
import { ProfileProvider } from "../state/ProfileContext";
import { JOB, NEEDS_REVIEW_ELIGIBILITY, recommendationItem } from "../test/fixtures";
import { JobCard } from "./JobCard";
import { Layout } from "./Layout";
import { RequirementBreakdown } from "./RequirementBreakdown";
import { VerdictBadge } from "./ui";

afterEach(cleanup);

describe("verdict badges", () => {
  it.each(VERDICT_ORDER)("show %s with a glyph and its text label, never colour alone", (state: EligibilityState) => {
    const { container } = render(<VerdictBadge state={state} />);
    const badge = container.querySelector(".verdict")!;
    expect(badge.textContent).toBe(VERDICTS[state].label);
    expect(badge.querySelector("svg[aria-hidden='true']")).not.toBeNull();
  });
});

describe("requirement breakdown presentation", () => {
  it("counts results only from the API's own rows", () => {
    render(<RequirementBreakdown eligibility={NEEDS_REVIEW_ELIGIBILITY} />);
    expect(screen.getByText("1 passed · 1 failed · 1 not verified")).toBeTruthy();
  });

  it("explains only the rows that need attention", () => {
    render(<RequirementBreakdown eligibility={NEEDS_REVIEW_ELIGIBILITY} />);
    const rows = within(screen.getByRole("list", { name: "Requirement checks" })).getAllByRole("listitem");
    // Source-stated rule-check pass: no explanation. AI-inconclusive and prose-derived fail: explained.
    expect(within(rows[0]!).queryByText(/Why this needs your attention/)).toBeNull();
    expect(within(rows[1]!).getByText(/Why this needs your attention/)).toBeTruthy();
    expect(within(rows[2]!).getByText(/Why this needs your attention/)).toBeTruthy();
  });
});

describe("job card", () => {
  it("never invents a logo image and shows the API's verdict when evaluated", () => {
    const evaluation = { item: recommendationItem(NEEDS_REVIEW_ELIGIBILITY), group: "needs_review" as const };
    const { container } = render(<JobCard job={JOB} evaluation={evaluation} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector(".job-card__logo")!.textContent).toBe("A");
    expect(screen.getByText("Needs review", { selector: ".verdict" })).toBeTruthy();
    expect(screen.getByText("Relevance 43/100")).toBeTruthy();
  });

  it("shows no verdict when nothing was evaluated", () => {
    const { container } = render(<JobCard job={JOB} />);
    expect(container.querySelector(".verdict")).toBeNull();
  });
});

describe("landing page", () => {
  it("labels its product preview as an illustration and promises no automatic applications", () => {
    render(<Landing />);
    expect(screen.getByText("Illustration, not a real evaluation")).toBeTruthy();
    expect(screen.getByText(/never submits an application/)).toBeTruthy();
    expect(screen.getByText(/synthetic demo catalogue/)).toBeTruthy();
    expect(screen.queryByText(/guarantee/i)).toBeNull();
  });
});

describe("mobile navigation", () => {
  it("opens and closes the menu, reporting its state", () => {
    render(
      <ProfileProvider>
        <Layout route={{ name: "dashboard" }}>
          <p>Body</p>
        </Layout>
      </ProfileProvider>,
    );
    const toggle = screen.getByRole("button", { name: "Menu" });
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(nav.className).not.toContain("nav--open");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(nav.className).toContain("nav--open");
    fireEvent.click(within(nav).getByText("Opportunities"));
    expect(nav.className).not.toContain("nav--open");
  });
});
