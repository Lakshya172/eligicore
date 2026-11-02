import type { JobRead } from "../api/types";
import type { Evaluation } from "../lib/evaluations";
import { JOB_TYPE_LABEL, formatDate } from "../lib/jobs";
import { Link } from "../router";
import { Badge, VerdictBadge } from "./ui";

export function JobCard({ job, evaluation }: { job: JobRead; evaluation?: Evaluation }) {
  const deadline = formatDate(job.deadline);
  const score = evaluation?.item.match.match_score;
  return (
    <article className="card job-card">
      <div className="job-card__top">
        <div className="job-card__logo" aria-hidden="true">
          {job.company_name.replace(/^(Example|Sample)\s+/i, "").charAt(0).toUpperCase()}
        </div>
        {evaluation && <VerdictBadge state={evaluation.item.eligibility.eligibility_state} />}
      </div>
      <h3 className="job-card__title">
        <Link to={`opportunities/${encodeURIComponent(job.id)}`} className="stretched-link">
          {job.role_title}
        </Link>
      </h3>
      <p className="job-card__company">{job.company_name}</p>
      <ul className="job-card__meta">
        {job.location && <li>{job.location}</li>}
        <li>{JOB_TYPE_LABEL[job.job_type]}</li>
        {deadline && <li>Apply by {deadline}</li>}
      </ul>
      <div className="job-card__footer">
        <Badge tone={job.status === "ACTIVE" ? "accent" : "neutral"}>
          {job.status === "ACTIVE" ? "Open" : job.status.charAt(0) + job.status.slice(1).toLowerCase()}
        </Badge>
        <span className="job-card__source">Source: {job.source}</span>
        {score != null && (
          <span className="job-card__score" title="Relevance to your skills and experience. Not an eligibility score.">
            Relevance {score.toFixed(0)}/100
          </span>
        )}
      </div>
    </article>
  );
}
