import type { JobEligibility } from "../api/types";
import {
  CONFIDENCE_LABEL,
  METHOD_LABEL,
  PROVENANCE_LABEL,
  REQUIREMENT_STATUS,
  VERDICTS,
  reviewReason,
} from "../lib/eligibility";
import { Badge, VerdictBadge } from "./ui";

/** The verdict and every requirement behind it, exactly as the API returned them. */
export function RequirementBreakdown({ eligibility }: { eligibility: JobEligibility }) {
  const verdict = VERDICTS[eligibility.eligibility_state];
  const rows = eligibility.requirement_breakdown;

  return (
    <div className="breakdown">
      <div className={`verdict-panel verdict-panel--${verdict.tone}`}>
        <VerdictBadge state={eligibility.eligibility_state} />
        <p className="verdict-panel__summary">{eligibility.summary}</p>
        <p className="verdict-panel__meaning">{verdict.meaning}</p>
      </div>

      {rows.length === 0 ? (
        <p className="muted">This job states no structured eligibility requirements.</p>
      ) : (
        <ul className="requirements" aria-label="Requirement checks">
          {rows.map((row, index) => {
            const status = REQUIREMENT_STATUS[row.status];
            const reason = reviewReason(row);
            return (
              <li key={`${row.requirement_type}-${index}`} className="requirement">
                <div className="requirement__head">
                  <div>
                    <p className="requirement__title">{row.requirement}</p>
                    <p className="requirement__value">
                      Your profile: <span>{row.candidate_value ?? "Not provided"}</span>
                    </p>
                  </div>
                  <Badge tone={status.tone}>{status.label}</Badge>
                </div>
                <p className="requirement__note">{row.note}</p>
                {row.evidence && (
                  <blockquote className="requirement__evidence">
                    <span className="requirement__evidence-label">From the job description</span>
                    “{row.evidence}”
                  </blockquote>
                )}
                {reason && <p className="requirement__review">{reason}</p>}
                <div className="requirement__tags">
                  <Badge tone={row.method === "ai_reasoning" ? "warning" : "neutral"}>
                    {METHOD_LABEL[row.method]}
                  </Badge>
                  <Badge tone={row.provenance === "PROSE_DERIVED" ? "warning" : "neutral"}>
                    {PROVENANCE_LABEL[row.provenance]}
                  </Badge>
                  <Badge>{CONFIDENCE_LABEL[row.confidence]}</Badge>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
