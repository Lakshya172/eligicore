import { api, ApiError } from "../api/client";
import type { JobRead } from "../api/types";
import { BriefcaseIcon, CalendarIcon, ExternalIcon, MapPinIcon } from "../components/icons";
import { companyInitial } from "../components/JobCard";
import { RequirementBreakdown } from "../components/RequirementBreakdown";
import { Badge, Card, CatalogueNotice, EmptyState, ErrorState, Spinner } from "../components/ui";
import { evaluateJobs } from "../lib/evaluations";
import { JOB_TYPE_LABEL, employerNotes, formatDate, safeExternalUrl, statedRequirements } from "../lib/jobs";
import { hasEvaluableData } from "../lib/profile";
import { useAsync } from "../lib/useAsync";
import { Link } from "../router";
import { useProfile } from "../state/ProfileContext";

function Eligibility({ job }: { job: JobRead }) {
  const { profile, isSample, revision } = useProfile();
  const evaluable = hasEvaluableData(profile);
  const result = useAsync(
    (signal) => evaluateJobs(profile ?? {}, [job.id], signal),
    [revision, job.id],
    evaluable,
  );

  if (!profile || !evaluable) {
    return (
      <EmptyState
        title="See whether you're eligible"
        action={
          <Link to="profile" className="button button--primary">
            Add your profile
          </Link>
        }
      >
        <p>Add your education details to check them against this role's requirements.</p>
      </EmptyState>
    );
  }
  if (result.status === "loading" || result.status === "idle") {
    return (
      <div className="centered">
        <Spinner label="Evaluating" />
        <p className="muted">Checking each requirement…</p>
      </div>
    );
  }
  if (result.status === "error") {
    return <ErrorState error={result.error} onRetry={result.retry} title="We couldn't check your eligibility" />;
  }
  const evaluation = result.data.get(job.id);
  if (!evaluation) {
    return <p className="muted">This role could not be evaluated.</p>;
  }
  const { match } = evaluation.item;
  return (
    <>
      {isSample && (
        <p className="notice notice--warning">
          Evaluated against the <strong>fictional sample profile</strong>, not a real student.
        </p>
      )}
      <RequirementBreakdown eligibility={evaluation.item.eligibility} />
      {match.required_skill_count > 0 && (
        <div className="skills-match">
          <h3 className="subheading">Skills this role lists</h3>
          <p className="fineprint">Skills affect relevance ranking only. They never decide eligibility.</p>
          <div className="chips">
            {match.matched_required_skills.map((skill) => (
              <span key={skill} className="chip chip--matched">✓ {skill}</span>
            ))}
            {match.missing_required_skills.map((skill) => (
              <span key={skill} className="chip">{skill}</span>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

export function OpportunityDetail({ jobId }: { jobId: string }) {
  const job = useAsync((signal) => api.getJob(jobId, signal), [jobId]);

  if (job.status === "error") {
    const missing = job.error instanceof ApiError && job.error.status === 404;
    return (
      <div className="page">
        <Link to="opportunities" className="back-link">← All opportunities</Link>
        {missing ? (
          <EmptyState
            title="This opportunity doesn't exist"
            action={<Link to="opportunities" className="button button--secondary">Browse opportunities</Link>}
          >
            <p>It may have been removed from the catalogue, or the link is incorrect.</p>
          </EmptyState>
        ) : (
          <ErrorState error={job.error} onRetry={job.retry} title="We couldn't load this opportunity" />
        )}
      </div>
    );
  }
  if (job.status !== "success") {
    return (
      <div className="page centered page--loading">
        <Spinner label="Loading opportunity" />
      </div>
    );
  }

  const data = job.data;
  const requirements = statedRequirements(data);
  const notes = employerNotes(data);
  const applyUrl = safeExternalUrl(data.apply_link);
  const deadline = formatDate(data.deadline);

  return (
    <div className="page">
      <Link to="opportunities" className="back-link">← All opportunities</Link>
      <header className="detail-header">
        <div className="detail-header__logo" aria-hidden="true">
          {companyInitial(data.company_name)}
        </div>
        <div className="detail-header__body">
          <h1 className="page-title">{data.role_title}</h1>
          <p className="detail-header__company">{data.company_name}</p>
          <ul className="detail-header__meta">
            <li>
              <Badge tone={data.is_active ? "accent" : "neutral"}>{data.is_active ? "Open" : data.status}</Badge>
            </li>
            <li>
              <BriefcaseIcon size={14} />
              {JOB_TYPE_LABEL[data.job_type]}
            </li>
            {data.location && (
              <li>
                <MapPinIcon size={14} />
                {data.location}
              </li>
            )}
            {deadline && (
              <li>
                <CalendarIcon size={14} />
                Apply by {deadline}
              </li>
            )}
          </ul>
        </div>
      </header>
      <CatalogueNotice />

      <div className="detail-grid">
        <div className="detail-grid__main">
          <Card>
            <h2 className="card__title">Your eligibility</h2>
            <Eligibility job={data} />
          </Card>

          <Card>
            <h2 className="card__title">About the role</h2>
            {data.description ? (
              <p className="description">{data.description}</p>
            ) : (
              <p className="muted">The employer provided no description.</p>
            )}
            <p className="fineprint">
              The description is shown for information. EligiCore evaluates only the requirements
              listed under "Stated requirements".
            </p>
          </Card>
        </div>

        <aside className="detail-grid__side">
          <Card>
            <h2 className="card__title">Stated requirements</h2>
            {requirements.length === 0 ? (
              <p className="muted">This role states no structured eligibility requirements.</p>
            ) : (
              <dl className="facts">
                {requirements.map((item) => (
                  <div key={item.label} className="facts__row">
                    <dt>{item.label}</dt>
                    <dd>{item.value}</dd>
                  </div>
                ))}
              </dl>
            )}
            {data.required_skills.length > 0 && (
              <>
                <h3 className="subheading">Skills listed</h3>
                <div className="chips">
                  {data.required_skills.map((skill) => (
                    <span key={skill} className="chip">{skill}</span>
                  ))}
                </div>
              </>
            )}
            {notes && (
              <div className="employer-notes">
                <h3 className="subheading">Employer notes</h3>
                <p>{notes}</p>
                <p className="fineprint">Free-text notes are shown as written and are not evaluated.</p>
              </div>
            )}
          </Card>

          <Card>
            <h2 className="card__title">Apply</h2>
            {applyUrl ? (
              <>
                <a className="button button--primary button--block" href={applyUrl} target="_blank" rel="noopener noreferrer">
                  Open employer's application page
                  <ExternalIcon size={15} />
                  <span className="visually-hidden"> (opens in a new tab)</span>
                </a>
                <p className="fineprint">
                  You apply on the employer's own site. EligiCore never submits applications for you.
                  In this demo catalogue the link is a placeholder.
                </p>
              </>
            ) : (
              <p className="muted">No application link was provided for this role.</p>
            )}
            <p className="fineprint">Source: {data.source}. Last verified {formatDate(data.last_verified_at)}.</p>
          </Card>
        </aside>
      </div>
    </div>
  );
}
