import { api } from "../api/client";
import type { RecommendationItem } from "../api/types";
import { ArrowRightIcon, CheckIcon, CrossIcon, QuestionIcon } from "../components/icons";
import { Badge, Card, CatalogueNotice, EmptyState, ErrorState, PageHeader, SectionHead, Spinner, VerdictBadge } from "../components/ui";
import { JOB_TYPE_LABEL } from "../lib/jobs";
import { hasEvaluableData } from "../lib/profile";
import { useAsync } from "../lib/useAsync";
import { Link } from "../router";
import { useProfile } from "../state/ProfileContext";

interface CatalogueStats {
  open: number;
  internships: number;
  fullTime: number;
  notStated: number;
  closed: number;
}

async function loadStats(signal: AbortSignal): Promise<CatalogueStats> {
  // Totals only: limit=1 keeps each response tiny, and `total` ignores pagination.
  const [open, internships, fullTime, notStated, closed] = await Promise.all([
    api.listJobs({ isActive: true, limit: 1 }, signal),
    api.listJobs({ isActive: true, jobType: "INTERNSHIP", limit: 1 }, signal),
    api.listJobs({ isActive: true, jobType: "FULL_TIME", limit: 1 }, signal),
    api.listJobs({ isActive: true, jobType: "UNKNOWN", limit: 1 }, signal),
    api.listJobs({ isActive: false, limit: 1 }, signal),
  ]);
  return {
    open: open.total,
    internships: internships.total,
    fullTime: fullTime.total,
    notStated: notStated.total,
    closed: closed.total,
  };
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="stat">
      <p className="stat__value">{value}</p>
      <p className="stat__label">{label}</p>
    </div>
  );
}

function RecommendationRow({ item }: { item: RecommendationItem }) {
  const { eligibility, match } = item;
  return (
    <li className="rec-row">
      <span className="rec-row__logo" aria-hidden="true">
        {eligibility.company_name.replace(/^(Example|Sample)\s+/i, "").charAt(0).toUpperCase()}
      </span>
      <div className="rec-row__main">
        <Link to={`opportunities/${encodeURIComponent(eligibility.job_id)}`} className="rec-row__title">
          {eligibility.role_title}
        </Link>
        <p className="rec-row__company">{eligibility.company_name}</p>
      </div>
      <div className="rec-row__side">
        {match.match_score != null && (
          <span className="rec-row__score" title="Relevance to your skills and experience. Not an eligibility score.">
            Relevance {match.match_score.toFixed(0)}
          </span>
        )}
        <VerdictBadge state={eligibility.eligibility_state} />
      </div>
    </li>
  );
}

function Recommendations() {
  const { profile, isSample, revision } = useProfile();
  const evaluable = hasEvaluableData(profile);
  const result = useAsync(
    (signal) => api.recommendations(profile ?? {}, undefined, signal),
    [revision],
    evaluable,
  );

  if (!profile || !evaluable) {
    return (
      <Card>
        <EmptyState
          title="Add your profile to see your eligibility"
          icon={<CheckIcon size={20} />}
          action={
            <Link to="profile" className="button button--primary">
              Add your profile
            </Link>
          }
        >
          <p>
            EligiCore checks each opening's stated requirements against your degree, graduation
            year, grade and backlogs. Nothing is evaluated until you provide them.
          </p>
        </EmptyState>
      </Card>
    );
  }

  if (result.status === "loading" || result.status === "idle") {
    return (
      <Card className="centered">
        <Spinner label="Evaluating your eligibility" />
        <p className="muted">Checking requirements across the catalogue…</p>
      </Card>
    );
  }
  if (result.status === "error") {
    return (
      <Card>
        <ErrorState error={result.error} onRetry={result.retry} title="We couldn't evaluate your profile" />
      </Card>
    );
  }

  const data = result.data;
  // Labels name exactly what each API group contains (app/schemas/matching.py): `ranked` holds
  // ELIGIBLE and LIKELY_ELIGIBLE, `needs_review` holds NEEDS_REVIEW and UNKNOWN.
  const groups = [
    { key: "ranked", label: "Eligible or likely eligible", tone: "success", count: data.ranked.length, icon: <CheckIcon size={14} /> },
    { key: "needs_review", label: "Need review or unverified", tone: "warning", count: data.needs_review.length, icon: <QuestionIcon size={14} /> },
    { key: "not_eligible", label: "Not eligible", tone: "danger", count: data.not_eligible.length, icon: <CrossIcon size={14} /> },
  ] as const;
  const total = groups.reduce((sum, group) => sum + group.count, 0);

  return (
    <>
      <Card>
        <SectionHead
          title="Your eligibility"
          action={isSample ? <Badge tone="warning">Sample profile (fictional)</Badge> : undefined}
        >
          <p>
            {data.jobs_considered} open roles evaluated
            {data.jobs_not_considered > 0 && ` (${data.jobs_not_considered} more not evaluated in this pass)`}.
          </p>
        </SectionHead>
        {total > 0 && (
          <div className="distribution" aria-hidden="true">
            {groups.map((group) =>
              group.count > 0 ? (
                <span
                  key={group.key}
                  className={`distribution__segment distribution__segment--${group.tone}`}
                  style={{ flexGrow: group.count }}
                />
              ) : null,
            )}
          </div>
        )}
        <div className="summary-grid">
          {groups.map((group) => (
            <div key={group.key} className={`summary-tile summary-tile--${group.tone}`}>
              <span className="summary-tile__icon" aria-hidden="true">
                {group.icon}
              </span>
              <p className="summary-tile__value">{group.count}</p>
              <p className="summary-tile__label">{group.label}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <SectionHead
          title="Top matches among roles you qualify for"
          action={
            <Link to="opportunities" className="text-link">
              View all <ArrowRightIcon size={14} />
            </Link>
          }
        />
        {data.ranked.length === 0 ? (
          <p className="muted">
            No role is eligible or likely eligible yet. Check the roles that need review — missing
            profile values are the most common reason.
          </p>
        ) : (
          <ul className="rec-list" aria-label="Top matches">
            {data.ranked.slice(0, 5).map((item) => (
              <RecommendationRow key={item.eligibility.job_id} item={item} />
            ))}
          </ul>
        )}
        <p className="fineprint">
          Ranked by relevance to your skills and experience, within the eligible and likely eligible
          roles. Each badge shows that role's own verdict. Relevance never affects eligibility.
        </p>
      </Card>

      {data.needs_review.length > 0 && (
        <Card>
          <SectionHead title="Worth a closer look">
            <p>These roles have at least one requirement that could not be verified.</p>
          </SectionHead>
          <ul className="rec-list" aria-label="Roles to review">
            {data.needs_review.slice(0, 5).map((item) => (
              <RecommendationRow key={item.eligibility.job_id} item={item} />
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}

export function Dashboard() {
  const stats = useAsync(loadStats, []);
  const { profile, isSample } = useProfile();
  return (
    <div className="page">
      <PageHeader
        eyebrow="Dashboard"
        title="Your opportunities at a glance"
        actions={
          <>
            <Link to="profile" className="button button--secondary">
              {profile ? (isSample ? "Edit sample profile" : "Edit profile") : "Add profile"}
            </Link>
            <Link to="opportunities" className="button button--primary">
              Explore opportunities
            </Link>
          </>
        }
      >
        <p>Your eligibility across the catalogue, with the reasons behind every verdict.</p>
      </PageHeader>
      <CatalogueNotice />

      <div className="dashboard-grid">
        <div className="dashboard-grid__main">
          <Recommendations />
        </div>
        <aside className="dashboard-grid__side">
          <Card>
            <SectionHead
              title="Catalogue overview"
              action={
                <Link to="opportunities" className="text-link">
                  Explore <ArrowRightIcon size={14} />
                </Link>
              }
            />
            {stats.status === "error" ? (
              <ErrorState error={stats.error} onRetry={stats.retry} />
            ) : stats.status === "success" ? (
              stats.data.open === 0 ? (
                <EmptyState title="No open opportunities yet">
                  <p>
                    The catalogue is empty. Load the demo catalogue with{" "}
                    <code>python -m app.cli seed-catalogue</code>.
                  </p>
                </EmptyState>
              ) : (
                <div className="stats">
                  <Stat label="Open roles" value={stats.data.open} />
                  <Stat label={JOB_TYPE_LABEL.INTERNSHIP + "s"} value={stats.data.internships} />
                  <Stat label={JOB_TYPE_LABEL.FULL_TIME + " roles"} value={stats.data.fullTime} />
                  {stats.data.notStated > 0 && <Stat label="Type not stated" value={stats.data.notStated} />}
                  <Stat label="Closed or expired" value={stats.data.closed} />
                </div>
              )
            ) : (
              <div className="centered">
                <Spinner />
              </div>
            )}
          </Card>

          <Card className="card--muted">
            <h2 className="section-head__title">Reading your results</h2>
            <ul className="legend" aria-label="Verdict examples">
              <li>
                <VerdictBadge state="ELIGIBLE" /> Every stated requirement passed a rule check.
              </li>
              <li>
                <VerdictBadge state="NEEDS_REVIEW" /> Something couldn't be verified — check it yourself.
              </li>
              <li>
                <VerdictBadge state="NOT_ELIGIBLE" /> A requirement the employer states failed a rule check.
              </li>
            </ul>
            <Link to="about" className="text-link">
              All five verdicts explained <ArrowRightIcon size={14} />
            </Link>
          </Card>
        </aside>
      </div>
    </div>
  );
}
