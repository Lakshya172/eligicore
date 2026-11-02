import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Landing } from "../pages/Landing";
import { OpportunityDetail } from "../pages/OpportunityDetail";
import { ProfileProvider } from "../state/ProfileContext";
import styles from "../styles.css?raw";
import { JOB } from "../test/fixtures";
import { Layout } from "./Layout";

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

function renderShell(name: "landing" | "dashboard") {
  return render(
    <ProfileProvider>
      <Layout route={{ name }}>
        <p>Body</p>
      </Layout>
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

describe("app shell", () => {
  it("uses the editorial top bar on the landing page and the sidebar everywhere else", () => {
    const { container, unmount } = renderShell("landing");
    expect(container.querySelector(".app--marketing")).not.toBeNull();
    unmount();
    const workspace = renderShell("dashboard");
    expect(workspace.container.querySelector(".app--workspace")).not.toBeNull();
  });

  it("keeps each navigation link's accessible name to its text, with icons hidden", () => {
    renderShell("dashboard");
    const nav = screen.getByRole("navigation", { name: "Primary" });
    for (const name of ["Dashboard", "Opportunities", "Profile", "How it works"]) {
      expect(within(nav).getByRole("link", { name })).toBeTruthy();
    }
    expect(within(nav).getByRole("link", { name: "Dashboard" }).getAttribute("aria-current")).toBe("page");
    for (const icon of nav.querySelectorAll(".nav__icon")) {
      expect(icon.getAttribute("aria-hidden")).toBe("true");
    }
  });
});

describe("landing hero", () => {
  it("states the product promise in plain words", () => {
    render(<Landing />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.textContent).toBe("Know where you stand.Before you apply.");
    expect(
      screen.getByText(
        "EligiCore helps students understand opportunity requirements, evaluate eligibility, and prepare with clarity.",
        { normalizer: (text) => text.replace(/\s+/g, " ").trim() },
      ),
    ).toBeTruthy();
  });
});

describe("job details breadcrumb", () => {
  it("links back to the catalogue and marks the current role", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => (url.startsWith("/api/v1/jobs/") ? json(JOB) : json({}, 500))));
    render(
      <ProfileProvider>
        <OpportunityDetail jobId={JOB.id} />
      </ProfileProvider>,
    );
    const crumbs = await screen.findByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumbs).getByRole("link", { name: "Opportunities" })).toBeTruthy();
    expect(within(crumbs).getByText(JOB.role_title).getAttribute("aria-current")).toBe("page");
  });
});

describe("stylesheet guarantees", () => {
  it("loads no external fonts or assets", () => {
    // Guards against a blank import making every assertion below vacuous.
    expect(styles).toContain("--bronze: #b78a60");
    expect(styles).not.toMatch(/@import|@font-face|url\(\s*["']?https?:/i);
  });

  it("removes motion for people who ask for less of it", () => {
    const block = styles.slice(styles.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(block).toContain("animation-duration: 0.01ms !important");
    expect(block).toContain("transition-duration: 0.01ms !important");
  });

  it("draws the keyboard focus ring as an outline that component shadows cannot hide", () => {
    expect(styles).toMatch(/:focus-visible\s*\{\s*outline: 2px solid var\(--bronze-light\)/);
  });
});
