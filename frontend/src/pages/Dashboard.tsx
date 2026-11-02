import { api } from "../api/client";
import type { RecommendationItem } from "../api/types";
import { Badge, Card, CatalogueNotice, EmptyState, ErrorState, PageHeader, Spinner, VerdictBadge } from "../components/ui";
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
      <div className="rec-row__main">
        <Link to={`opportunities/${encodeURIComponent(eligibility.job_id)}`} className="rec-row__title">
          {eligibility.role_title}
        </Link>
        <p className="rec-row__company">{eligibility.company_name}</p>
      </div>
      <div className="rec-row__side">
        <VerdictBadge state={eligibility.eligibility_state} />
        {match.match_score != null && (
          <span className="rec-row__score" title="Relevance to your skills and experience. Not an eligibility score.">
            Relevance {match.match_score.toFixed(0)}
          </span>
        )}
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
  const groups = [
    { key: "ranked", label: "Eligible", tone: "success", count: data.ranked.length },
    { key: "needs_review", label: "Need review", tone: "warning", count: data.needs_review.length },
    { key: "not_eligible", label: "Not eligible", tone: "danger", count: data.not_eligible.length },
  ] as const;

  return (
    <>
      <Card>
        <div className="card__head">
          <div>
            <h2 className="card__title">Your eligibility</h2>
            <p className="muted">
              {data.jobs_considered} open roles evaluated
              {data.jobs_not_considered > 0 && ` (${data.jobs_not_considered} more not evaluated in this pass)`}.
            </p>
          </div>
          {isSample && <Badge tone="warning">Sample profile (fictional)</Badge>}
        </div>
        <div className="summary-grid">
          {groups.map((group) => (
            <div key={group.key} className={`summary-tile summary-tile--${group.tone}`}>
              <p className="summary-tile__value">{group.count}</p>
              <p className="summary-tile__label">{group.label}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <div className="card__head">
          <h2 className="card__title">Top matches you're eligible for</h2>
          <Link to="opportunities" className="text-link">
            View all
          </Link>
        </div>
        {data.ranked.length === 0 ? (
          <p className="muted">
            No role is fully eligible yet. Check the roles that need review — missing profile values
            are the most common reason.
          </p>
        ) : (
          <ul className="rec-list">
            {data.ranked.slice(0, 5).map((item) => (
              <RecommendationRow key={item.eligibility.job_id} item={item} />
            ))}
          </ul>
        )}
        <p className="fineprint">
          Ranked by relevance to your skills and experience, within the roles you are eligible for.
          Relevance never affects eligibility.
        </p>
      </Card>

      {data.needs_review.length > 0 && (
        <Card>
          <div className="card__head">
            <h2 className="card__title">Worth a closer look</h2>
          </div>
          <ul className="rec-list">
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
  return (
    <div className="page">
      <PageHeader eyebrow="Dashboard" title="Your opportunities at a glance" />
      <CatalogueNotice />

      <Card>
        <div className="card__head">
          <h2 className="card__title">Catalogue overview</h2>
          <Link to="opportunities" className="text-link">
            Explore
          </Link>
        </div>
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

      <Recommendations />
    </div>
  );
}
