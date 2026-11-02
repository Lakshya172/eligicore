import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, describeError } from "./client";

function respond(status: number, body: unknown, asJson = true) {
  return vi.fn().mockResolvedValue(
    new Response(asJson ? JSON.stringify(body) : String(body), {
      status,
      headers: { "Content-Type": asJson ? "application/json" : "text/plain" },
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("lists jobs with only the filters the API supports", async () => {
    const fetchMock = respond(200, { items: [], total: 0, limit: 100, offset: 0 });
    vi.stubGlobal("fetch", fetchMock);
    await api.listJobs({ isActive: false, jobType: "INTERNSHIP" });
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/jobs?is_active=false&job_type=INTERNSHIP&limit=100&offset=0", {
      signal: undefined,
    });
  });

  it("sends the profile in the request body, never the URL", async () => {
    const fetchMock = respond(200, { ranked: [], needs_review: [], not_eligible: [], not_open: [] });
    vi.stubGlobal("fetch", fetchMock);
    await api.recommendations({ backlogs: 0 }, ["job-1"]);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/v1/recommendations");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ profile: { backlogs: 0 }, job_ids: ["job-1"] });
  });

  it("surfaces the API's error envelope", async () => {
    vi.stubGlobal(
      "fetch",
      respond(404, { error: "HTTP_ERROR", message: "Job not found.", request_id: "req-1", details: [] }),
    );
    const error = await api.getJob("missing").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, code: "HTTP_ERROR", message: "Job not found.", requestId: "req-1" });
  });

  it("explains a backend that cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await api.health().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).isNetworkError).toBe(true);
    expect(describeError(error)).toMatch(/could not be reached/);
  });

  it("handles a proxy's non-JSON gateway error", async () => {
    vi.stubGlobal("fetch", respond(502, "Bad Gateway", false));
    const error = await api.health().catch((caught: unknown) => caught);
    expect(describeError(error)).toMatch(/unavailable/);
  });
});
