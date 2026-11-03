import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProfileProvider } from "../state/ProfileContext";
import { NEEDS_REVIEW_ELIGIBILITY, recommendationItem, recommendationResponse } from "../test/fixtures";
import { Dashboard } from "./Dashboard";

function json(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
}

beforeEach(() => {
  window.sessionStorage.setItem(
    "eligicore.profile.v1",
    JSON.stringify({ profile: { backlogs: 0 }, isSample: true, revision: 1 }),
  );
});

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe("Dashboard", () => {
  it("labels each total with exactly the verdicts its API group contains", async () => {
    const likely = recommendationItem({ ...NEEDS_REVIEW_ELIGIBILITY, eligibility_state: "LIKELY_ELIGIBLE" });
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        url.startsWith("/api/v1/jobs")
          ? json({ items: [], total: 1, limit: 1, offset: 0 })
          : json(recommendationResponse({ ranked: [likely] })),
      ),
    );
    render(
      <ProfileProvider>
        <Dashboard />
      </ProfileProvider>,
    );

    expect(await screen.findByText("Eligible or likely eligible")).toBeTruthy();
    expect(screen.getByText("Need review or unverified")).toBeTruthy();
    // The row shows the job's own verdict, never a rounded-up "Eligible". Scoped to the results
    // list: the static legend beside it shows example badges by design.
    const results = within(screen.getByRole("list", { name: "Top matches" }));
    expect(results.getByText("Likely eligible", { selector: ".verdict" })).toBeTruthy();
    expect(results.queryByText("Eligible", { selector: ".verdict" })).toBeNull();
  });
});
