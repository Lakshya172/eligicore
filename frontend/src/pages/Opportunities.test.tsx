import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProfileProvider } from "../state/ProfileContext";
import { JOB, JOB_2, NEEDS_REVIEW_ELIGIBILITY, recommendationItem, recommendationResponse } from "../test/fixtures";
import { Opportunities } from "./Opportunities";

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

function renderPage() {
  return render(
    <ProfileProvider>
      <Opportunities />
    </ProfileProvider>,
  );
}

beforeEach(() => {
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Opportunities", () => {
  it("lists catalogue jobs, labels the demo catalogue and asks for a profile", async () => {
    const fetchMock = vi.fn((url: string) =>
      url.startsWith("/api/v1/jobs") ? json({ items: [JOB, JOB_2], total: 2, limit: 100, offset: 0 }) : json({}, 500),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    expect(await screen.findByText("Software Engineering Intern")).toBeTruthy();
    expect(screen.getByText("Backend Engineer")).toBeTruthy();
    expect(screen.getByText(/Every employer is fictional/)).toBeTruthy();
    expect(screen.getByText(/Eligibility isn't shown yet/)).toBeTruthy();
    // No profile: no evaluation request is made.
    expect(fetchMock.mock.calls.every(([url]) => String(url).startsWith("/api/v1/jobs"))).toBe(true);
  });

  it("filters by search in the browser", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ items: [JOB, JOB_2], total: 2, limit: 100, offset: 0 })));
    renderPage();
    await screen.findByText("Software Engineering Intern");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "remote" } });
    expect(screen.queryByText("Software Engineering Intern")).toBeNull();
    expect(screen.getByText("Backend Engineer")).toBeTruthy();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "nothing-matches" } });
    expect(screen.getByText("No opportunities match your search")).toBeTruthy();
  });

  it("shows verdicts from the API when a profile exists", async () => {
    window.sessionStorage.setItem(
      "eligicore.profile.v1",
      JSON.stringify({ profile: { backlogs: 1 }, isSample: true, revision: 1 }),
    );
    const fetchMock = vi.fn((url: string, _init?: RequestInit) => {
      void _init;
      return url.startsWith("/api/v1/jobs")
        ? json({ items: [JOB], total: 1, limit: 100, offset: 0 })
        : json(recommendationResponse({ needs_review: [recommendationItem(NEEDS_REVIEW_ELIGIBILITY)] }));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    expect(await screen.findByText("Needs review", { selector: ".verdict" })).toBeTruthy();
    expect(screen.getByText(/the fictional sample profile/)).toBeTruthy();
    const evaluationCall = fetchMock.mock.calls.find(([url]) => url === "/api/v1/recommendations");
    expect(JSON.parse(String(evaluationCall![1]!.body))).toEqual({
      profile: { backlogs: 1 },
      job_ids: ["job-1"],
    });
  });

  it("shows a recoverable error when the API is down", async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("Failed to fetch"));
    fetchMock.mockImplementation(() => json({ items: [JOB], total: 1, limit: 100, offset: 0 }));
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    expect(await screen.findByText("The EligiCore API isn't responding")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByText("Software Engineering Intern")).toBeTruthy());
  });
});
