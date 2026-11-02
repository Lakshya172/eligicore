import { api, MAX_RECOMMENDATION_JOBS } from "../api/client";
import type {
  CandidateProfile,
  RecommendationGroup,
  RecommendationItem,
  RecommendationResponse,
} from "../api/types";

export interface Evaluation {
  item: RecommendationItem;
  group: RecommendationGroup;
}

export const GROUPS: RecommendationGroup[] = ["ranked", "needs_review", "not_eligible", "not_open"];

/** Index a recommendation response by job id, remembering which group each job landed in. */
export function indexResponse(response: RecommendationResponse): Map<string, Evaluation> {
  const byJob = new Map<string, Evaluation>();
  for (const group of GROUPS) {
    for (const item of response[group]) {
      byJob.set(item.eligibility.job_id, { item, group });
    }
  }
  return byJob;
}

/**
 * Evaluate a profile against specific catalogue jobs through POST /recommendations, in
 * batches the API accepts. Each response embeds the unchanged eligibility verdict, so the
 * UI never computes or adjusts a verdict itself.
 */
export async function evaluateJobs(
  profile: CandidateProfile,
  jobIds: string[],
  signal?: AbortSignal,
): Promise<Map<string, Evaluation>> {
  const all = new Map<string, Evaluation>();
  for (let start = 0; start < jobIds.length; start += MAX_RECOMMENDATION_JOBS) {
    const batch = jobIds.slice(start, start + MAX_RECOMMENDATION_JOBS);
    const response = await api.recommendations(profile, batch, signal);
    for (const [jobId, evaluation] of indexResponse(response)) all.set(jobId, evaluation);
  }
  return all;
}
