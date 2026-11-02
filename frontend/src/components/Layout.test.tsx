import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ProfileProvider } from "../state/ProfileContext";
import { Layout } from "./Layout";

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

describe("Layout", () => {
  it("skips to content without changing the route", () => {
    window.location.hash = "#/opportunities";
    render(
      <ProfileProvider>
        <Layout route={{ name: "opportunities" }}>
          <p>Page body</p>
        </Layout>
      </ProfileProvider>,
    );
    fireEvent.click(screen.getByText("Skip to content"));
    expect(window.location.hash).toBe("#/opportunities");
    expect(document.activeElement?.id).toBe("main");
  });
});
