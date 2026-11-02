import { useMemo, useState } from "react";
import { api, describeError } from "../api/client";
import type { EligibilityState, JobType } from "../api/types";
import { JobCard } from "../components/JobCard";
import { Badge, CatalogueNotice, EmptyState, ErrorState, PageHeader, SkeletonCards, Spinner } from "../components/ui";
import { VERDICTS, VERDICT_ORDER } from "../lib/eligibility";
import { evaluateJobs } from "../lib/evaluations";
import { matchesSearch } from "../lib/jobs";
import { hasEvaluableData } from "../lib/profile";
import { useAsync } from "../lib/useAsync";
import { Link } from "../router";
import { useProfile } from "../state/ProfileContext";

type TypeFilter = "ALL" | JobType;
type StatusFilter = "open" | "closed";
type VerdictFilter = "ALL" | EligibilityState;

export function Opportunities() {
  const { profile, isSample, revision } = useProfile();
  const [query, setQuery] = useState("");
  const [jobType, setJobType] = useState<TypeFilter>("ALL");
  const [status, setStatus] = useState<StatusFilter>("open");
  const [verdict, setVerdict] = useState<VerdictFilter>("ALL");

  // Server-side filters: the two GET /jobs supports. The page size is the API maximum (100),
  // which covers the whole demo catalogue.
  const jobs = useAsync(
    (signal) =>
      api.listJobs(
        { isActive: status === "open", jobType: jobType === "ALL" ? undefined : jobType },
        signal,
      ),
    [status, jobType],
  );

  const jobIds = useMemo(
    () => (jobs.status === "success" ? jobs.data.items.map((job) => job.id) : []),
    [jobs],
  );
  const evaluable = hasEvaluableData(profile);
  const evaluations = useAsync(
    (signal) => evaluateJobs(profile ?? {}, jobIds, signal),
    [revision, jobIds.join(",")],
    evaluable && jobIds.length > 0,
  );
  const evaluationMap = evaluations.status === "success" ? evaluations.data : null;

  const visible = useMemo(() => {
    if (jobs.status !== "success") return [];
    return jobs.data.items.filter((job) => {
      if (!matchesSearch(job, query)) return false;
      if (verdict === "ALL" || !evaluationMap) return true;
      return evaluationMap.get(job.id)?.item.eligibility.eligibility_state === verdict;
    });
  }, [jobs, query, verdict, evaluationMap]);

  return (
    <div className="page">
      <PageHeader eyebrow="Opportunities" title="Explore opportunities">
        <p>Browse openings and see each employer's stated requirements.</p>
      </PageHeader>
      <CatalogueNotice />

      <div className="eval-banner" aria-live="polite">
        {!evaluable ? (
          <p>
            <strong>Eligibility isn't shown yet.</strong> <Link to="profile">Add your profile</Link>{" "}
            to see a verdict on every card.
          </p>
        ) : jobs.status === "error" || (jobs.status === "success" && jobIds.length === 0) ? null : evaluations.status ===
            "loading" || jobs.status !== "success" ? (
          <p className="eval-banner__loading">
            <Spinner label="Evaluating" /> Checking your eligibility
            {jobIds.length > 0 ? ` for ${jobIds.length} roles` : ""}…
          </p>
        ) : evaluations.status === "error" ? (
          <p className="eval-banner__error">
            Eligibility couldn't be checked: {describeError(evaluations.error)}{" "}
            <button type="button" className="text-button" onClick={evaluations.retry}>
              Try again
            </button>
          </p>
        ) : (
          <p>
            Eligibility shown for {isSample ? <Badge tone="warning">the fictional sample profile</Badge> : "your profile"}.
          </p>
        )}
      </div>

      <form className="filters" role="search" onSubmit={(event) => event.preventDefault()}>
        <label className="field field--grow">
          <span className="field__label">Search</span>
          <input
            type="search"
            className="input"
            placeholder="Role, company, location or skill"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className="field">
          <span className="field__label">Type</span>
          <select className="input" value={jobType} onChange={(event) => setJobType(event.target.value as TypeFilter)}>
            <option value="ALL">All types</option>
            <option value="INTERNSHIP">Internships</option>
            <option value="FULL_TIME">Full-time</option>
            <option value="UNKNOWN">Type not stated</option>
          </select>
        </label>
        <label className="field">
          <span className="field__label">Status</span>
          <select className="input" value={status} onChange={(event) => setStatus(event.target.value as StatusFilter)}>
            <option value="open">Open</option>
            <option value="closed">Closed or expired</option>
          </select>
        </label>
        <label className="field">
          <span className="field__label">Eligibility</span>
          <select
            className="input"
            value={verdict}
            disabled={!evaluationMap}
            onChange={(event) => setVerdict(event.target.value as VerdictFilter)}
          >
            <option value="ALL">Any verdict</option>
            {VERDICT_ORDER.map((state) => (
              <option key={state} value={state}>
                {VERDICTS[state].label}
              </option>
            ))}
          </select>
        </label>
      </form>

      {jobs.status === "error" ? (
        <ErrorState error={jobs.error} onRetry={jobs.retry} title="We couldn't load opportunities" />
      ) : jobs.status !== "success" ? (
        <SkeletonCards />
      ) : jobs.data.total === 0 ? (
        <EmptyState title={status === "open" ? "No open opportunities" : "No closed or expired opportunities"}>
          <p>
            {status === "open"
              ? "The catalogue has no open roles matching these filters."
              : "Nothing in the catalogue has closed or expired."}
          </p>
        </EmptyState>
      ) : visible.length === 0 ? (
        <EmptyState
          title="No opportunities match your search"
          action={
            <button
              type="button"
              className="button button--secondary"
              onClick={() => {
                setQuery("");
                setVerdict("ALL");
              }}
            >
              Clear search
            </button>
          }
        />
      ) : (
        <>
          <p className="result-count">
            Showing {visible.length} of {jobs.data.total} {status === "open" ? "open" : "closed or expired"} roles
          </p>
          <div className="job-grid">
            {visible.map((job) => (
              <JobCard key={job.id} job={job} evaluation={evaluationMap?.get(job.id)} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
