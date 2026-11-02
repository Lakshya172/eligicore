// The only module that talks to the backend. Every call goes to existing routes under
// /api/v1 (app/main.py, app/routers/*). Personal data is sent only in request bodies, never
// in URLs, and nothing returned here is written to the server.

import type {
  CandidateProfile,
  CandidateValidationResponse,
  ErrorResponse,
  HealthResponse,
  JobListResponse,
  JobRead,
  JobType,
  RecommendationResponse,
  ResumeParseResponse,
} from "./types";

export const API_BASE = "/api/v1";

/** The API's own limits: GET /jobs caps `limit` at 100, recommendations at 50 job ids. */
export const MAX_JOBS_PAGE = 100;
export const MAX_RECOMMENDATION_JOBS = 50;
/** ELIGICORE_MAX_RESUME_BYTES default (app/config.py). The server enforces it too. */
export const MAX_RESUME_BYTES = 5 * 1024 * 1024;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: ErrorResponse["details"];

  constructor(
    status: number,
    code: string,
    message: string,
    requestId: string | null = null,
    details: ErrorResponse["details"] = [],
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }

  /** True when the backend could not be reached at all. */
  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as ErrorResponse).error === "string" &&
    typeof (value as ErrorResponse).message === "string"
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(
      0,
      "NETWORK_ERROR",
      "The EligiCore API could not be reached. Check that the backend is running.",
    );
  }

  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    if (isErrorResponse(body)) {
      throw new ApiError(
        response.status,
        body.error,
        body.message,
        body.request_id ?? null,
        body.details ?? [],
      );
    }
    // A proxy answering for a stopped backend returns a non-JSON 5xx.
    throw new ApiError(
      response.status,
      "HTTP_ERROR",
      response.status >= 500
        ? "The EligiCore API is unavailable right now. Check that the backend is running."
        : `The request failed with status ${response.status}.`,
    );
  }
  return body as T;
}

function postJson<T>(path: string, payload: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
}

export interface JobFilters {
  isActive?: boolean;
  jobType?: JobType;
  limit?: number;
  offset?: number;
}

export const api = {
  health(signal?: AbortSignal): Promise<HealthResponse> {
    return request<HealthResponse>("/health", { signal });
  },

  listJobs(filters: JobFilters = {}, signal?: AbortSignal): Promise<JobListResponse> {
    const params = new URLSearchParams();
    params.set("is_active", String(filters.isActive ?? true));
    if (filters.jobType) params.set("job_type", filters.jobType);
    params.set("limit", String(filters.limit ?? MAX_JOBS_PAGE));
    params.set("offset", String(filters.offset ?? 0));
    return request<JobListResponse>(`/jobs?${params.toString()}`, { signal });
  },

  getJob(jobId: string, signal?: AbortSignal): Promise<JobRead> {
    return request<JobRead>(`/jobs/${encodeURIComponent(jobId)}`, { signal });
  },

  /** POST /recommendations. Omitting jobIds uses the API's default scope. */
  recommendations(
    profile: CandidateProfile,
    jobIds?: string[],
    signal?: AbortSignal,
  ): Promise<RecommendationResponse> {
    const payload = jobIds ? { profile, job_ids: jobIds } : { profile };
    return postJson<RecommendationResponse>("/recommendations", payload, signal);
  },

  validateProfile(
    profile: CandidateProfile,
    signal?: AbortSignal,
  ): Promise<CandidateValidationResponse> {
    return postJson<CandidateValidationResponse>("/candidates/validate", profile, signal);
  },

  parseResume(file: File, signal?: AbortSignal): Promise<ResumeParseResponse> {
    const form = new FormData();
    form.append("file", file);
    return request<ResumeParseResponse>("/resumes/parse", {
      method: "POST",
      body: form,
      signal,
    });
  },
};

/** A message suitable for showing to the student. Never includes submitted values. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Please try again.";
}

export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
