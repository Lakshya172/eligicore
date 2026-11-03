import type { JobRead } from "../api/types";
import type { Evaluation } from "../lib/evaluations";
import { JOB_TYPE_LABEL, formatDate } from "../lib/jobs";
import { Link } from "../router";
import { BriefcaseIcon, CalendarIcon, MapPinIcon } from "./icons";
import { Badge, VerdictBadge } from "./ui";

/** The initial shown in place of a logo. No employer logo is ever invented. */
export function companyInitial(name: string): string {
  return name.replace(/^(Example|Sample)\s+/i, "").charAt(0).toUpperCase();
}

export function JobCard({ job, evaluation }: { job: JobRead; evaluation?: Evaluation }) {
  const deadline = formatDate(job.deadline);
  const score = evaluation?.item.match.match_score;
  return (
    <article className="card job-card">
      <div className="job-card__top">
        <div className="job-card__logo" aria-hidden="true">
          {companyInitial(job.company_name)}
        </div>
        <div className="job-card__heading">
          <h3 className="job-card__title">
            <Link to={`opportunities/${encodeURIComponent(job.id)}`} className="stretched-link">
              {job.role_title}
            </Link>
          </h3>
          <p className="job-card__company">{job.company_name}</p>
        </div>
      </div>
      {evaluation && (
        <div className="job-card__verdict">
          <VerdictBadge state={evaluation.item.eligibility.eligibility_state} />
        </div>
      )}
      <ul className="job-card__meta">
        {job.location && (
          <li>
            <MapPinIcon size={14} />
            {job.location}
          </li>
        )}
        <li>
          <BriefcaseIcon size={14} />
          {JOB_TYPE_LABEL[job.job_type]}
        </li>
        {deadline && (
          <li>
            <CalendarIcon size={14} />
            Apply by {deadline}
          </li>
        )}
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
