import { describe, expect, it } from "vitest";
import { parseRoute } from "./router";

describe("parseRoute", () => {
  it("maps every screen", () => {
    expect(parseRoute("")).toEqual({ name: "landing" });
    expect(parseRoute("#/")).toEqual({ name: "landing" });
    expect(parseRoute("#/dashboard")).toEqual({ name: "dashboard" });
    expect(parseRoute("#/opportunities")).toEqual({ name: "opportunities" });
    expect(parseRoute("#/opportunities/abc%2D1")).toEqual({ name: "opportunity", jobId: "abc-1" });
    expect(parseRoute("#/profile/")).toEqual({ name: "profile" });
    expect(parseRoute("#/about")).toEqual({ name: "about" });
  });

  it("treats anything else as not found", () => {
    expect(parseRoute("#/nope")).toEqual({ name: "not-found" });
    expect(parseRoute("#/opportunities/a/b")).toEqual({ name: "not-found" });
    expect(parseRoute("#/profile/extra")).toEqual({ name: "not-found" });
  });
});
