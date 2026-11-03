import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SAMPLE_PROFILE } from "../lib/sampleProfile";
import { Dashboard } from "../pages/Dashboard";
import { Opportunities } from "../pages/Opportunities";
import { Profile } from "../pages/Profile";
import type { Route } from "../router";
import { ProfileProvider } from "../state/ProfileContext";
import { JOB, NEEDS_REVIEW_ELIGIBILITY, recommendationItem, recommendationResponse } from "../test/fixtures";
import { Layout } from "./Layout";

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

/** A fetch whose requests never settle, to observe the in-flight state. */
const pendingFetch = () => vi.fn<typeof fetch>(() => new Promise<Response>(() => {}));

function renderShell(route: Route) {
  return render(
    <ProfileProvider>
      <Layout route={route}>
        <p>Body</p>
      </Layout>
    </ProfileProvider>,
  );
}

function storeProfile(profile: unknown, isSample = false) {
  window.sessionStorage.setItem("eligicore.profile.v1", JSON.stringify({ profile, isSample, revision: 1 }));
}

beforeEach(() => {
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("quick navigation", () => {
  it("opens with Ctrl+K, filters pages, and navigates with Enter", async () => {
    renderShell({ name: "dashboard" });
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });

    const dialog = screen.getByRole("dialog", { name: "Quick navigation" });
    const input = within(dialog).getByRole("combobox", { name: "Go to page" });
    expect(document.activeElement).toBe(input);
    expect(within(dialog).getAllByRole("option")).toHaveLength(5);

    fireEvent.change(input, { target: { value: "resume" } });
    const options = within(dialog).getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual([expect.stringContaining("Profile")]);

    fireEvent.keyDown(input, { key: "Enter" });
    expect(window.location.hash).toBe("#/profile");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("moves the selection with the arrow keys and keeps Tab inside the dialog", () => {
    renderShell({ name: "dashboard" });
    fireEvent.click(screen.getByRole("button", { name: "Quick navigation" }));
    const input = screen.getByRole("combobox", { name: "Go to page" });
    const selected = () => screen.getAllByRole("option").findIndex((option) => option.getAttribute("aria-selected") === "true");

    expect(selected()).toBe(0);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(selected()).toBe(2);
    fireEvent.keyDown(input, { key: "ArrowUp" });
    expect(selected()).toBe(1);
    expect(input.getAttribute("aria-activedescendant")).toBe(screen.getAllByRole("option")[1]!.id);

    const tab = fireEvent.keyDown(input, { key: "Tab" });
    expect(tab).toBe(false); // default prevented: focus stays in the dialog
  });

  it("closes on Escape and returns focus to what opened it", async () => {
    renderShell({ name: "dashboard" });
    const trigger = screen.getByRole("button", { name: "Quick navigation" });
    trigger.focus();
    fireEvent.click(trigger);
    fireEvent.keyDown(screen.getByRole("combobox", { name: "Go to page" }), { key: "Escape" });

    expect(document.activeElement).toBe(trigger);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(window.location.hash).toBe("");
  });
});

describe("navigation indicator", () => {
  it("sits on the active destination and hides where none is active", () => {
    const { container, unmount } = renderShell({ name: "opportunity", jobId: "x" });
    const list = container.querySelector<HTMLElement>(".nav__list")!;
    expect(list.style.getPropertyValue("--nav-index")).toBe("1");
    expect(container.querySelector(".nav__indicator--hidden")).toBeNull();
    unmount();

    const landing = renderShell({ name: "landing" });
    expect(landing.container.querySelector(".nav__indicator--hidden")).not.toBeNull();
  });
});

describe("opportunities search shortcut", () => {
  it("focuses search on '/' but never while typing in another field", () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ items: [JOB], total: 1, limit: 100, offset: 0 })));
    render(
      <ProfileProvider>
        <Opportunities />
      </ProfileProvider>,
    );
    const search = screen.getByRole("searchbox");
    const type = screen.getByRole("combobox", { name: "Type" });

    type.focus();
    fireEvent.keyDown(type, { key: "/" });
    expect(document.activeElement).toBe(type);

    type.blur();
    fireEvent.keyDown(document.body, { key: "/" });
    expect(document.activeElement).toBe(search);
  });
});

describe("résumé drop zone", () => {
  function renderProfile() {
    render(
      <ProfileProvider>
        <Profile />
      </ProfileProvider>,
    );
    return screen.getByText(/Choose a résumé file/).closest("label")!;
  }

  it("rejects an unsupported dropped file without sending anything", () => {
    const fetchMock = pendingFetch();
    vi.stubGlobal("fetch", fetchMock);
    const zone = renderProfile();
    const file = new File(["text"], "notes.txt", { type: "text/plain" });

    fireEvent.drop(zone, { dataTransfer: { files: [file] } });
    expect(screen.getByText("Only PDF and DOCX résumés are supported.")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("asks for one file at a time", () => {
    const fetchMock = pendingFetch();
    vi.stubGlobal("fetch", fetchMock);
    const zone = renderProfile();
    const a = new File(["%PDF"], "a.pdf", { type: "application/pdf" });
    const b = new File(["%PDF"], "b.pdf", { type: "application/pdf" });

    fireEvent.drop(zone, { dataTransfer: { files: [a, b] } });
    expect(screen.getByText("Drop one résumé at a time.")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends a dropped PDF through the same single request and shows real, indeterminate progress", async () => {
    const fetchMock = pendingFetch();
    vi.stubGlobal("fetch", fetchMock);
    const zone = renderProfile();

    fireEvent.dragOver(zone, { dataTransfer: { dropEffect: "none" } });
    expect(zone.className).toContain("dropzone--dragging");
    expect(screen.getByText("Release to read this résumé")).toBeTruthy();

    const file = new File(["%PDF-1.4"], "fictional.pdf", { type: "application/pdf" });
    fireEvent.drop(zone, { dataTransfer: { files: [file] } });

    const progress = await screen.findByRole("progressbar", { name: "Reading résumé" });
    expect(progress.hasAttribute("aria-valuenow")).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]![0])).toContain("/api/v1/resumes/parse");
    expect(zone.className).not.toContain("dropzone--dragging");
  });
});

describe("profile save button", () => {
  it("shows a busy state and cannot submit twice", async () => {
    storeProfile(SAMPLE_PROFILE, true);
    const fetchMock = pendingFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(
      <ProfileProvider>
        <Profile />
      </ProfileProvider>,
    );
    const save = screen.getByRole("button", { name: "Save and check eligibility" });

    fireEvent.click(save);
    const busy = await screen.findByRole("button", { name: "Checking your profile…" });
    expect(busy.getAttribute("aria-busy")).toBe("true");
    expect((busy as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(busy);

    const validateCalls = fetchMock.mock.calls.filter(([url]) => String(url).includes("/candidates/validate"));
    expect(validateCalls).toHaveLength(1);
  });
});

describe("dashboard context", () => {
  it("states the profile the counts were computed from, and each count's share", async () => {
    storeProfile({
      education: [{ degree: "B.Tech", field_of_study: "Information Technology", grad_year: 2027, cgpa: 8.2, scale: "SCALE_10" }],
      backlogs: null,
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        url.startsWith("/api/v1/jobs")
          ? json({ items: [], total: 1, limit: 1, offset: 0 })
          : json(recommendationResponse({ ranked: [recommendationItem(NEEDS_REVIEW_ELIGIBILITY)] })),
      ),
    );
    render(
      <ProfileProvider>
        <Dashboard />
      </ProfileProvider>,
    );

    const context = await screen.findByLabelText("Evaluated against");
    expect(within(context).getByText("B.Tech · Information Technology")).toBeTruthy();
    expect(within(context).getByText("8.2 / 10")).toBeTruthy();
    // Blank stays "not stated": it is never shown as zero.
    expect(within(context).getByText("Not stated")).toBeTruthy();
    expect(screen.getByText("100% of evaluated")).toBeTruthy();
  });
});
