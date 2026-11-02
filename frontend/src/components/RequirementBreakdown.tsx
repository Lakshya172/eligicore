import type { ReactElement } from "react";
import type { JobEligibility, RequirementStatus } from "../api/types";
import {
  CONFIDENCE_LABEL,
  METHOD_LABEL,
  PROVENANCE_LABEL,
  REQUIREMENT_STATUS,
  VERDICTS,
  reviewReason,
} from "../lib/eligibility";
import { CheckIcon, CrossIcon, DocumentIcon, QuestionIcon, RuleIcon, SparkIcon } from "./icons";
import { Badge, VerdictBadge } from "./ui";

const STATUS_GLYPH: Record<RequirementStatus, ReactElement> = {
  PASS: <CheckIcon size={14} />,
  FAIL: <CrossIcon size={14} />,
  UNKNOWN: <QuestionIcon size={14} />,
};

/** The verdict and every requirement behind it, exactly as the API returned them. */
export function RequirementBreakdown({ eligibility }: { eligibility: JobEligibility }) {
  const verdict = VERDICTS[eligibility.eligibility_state];
  const rows = eligibility.requirement_breakdown;
  const counts = {
    PASS: rows.filter((row) => row.status === "PASS").length,
    FAIL: rows.filter((row) => row.status === "FAIL").length,
    UNKNOWN: rows.filter((row) => row.status === "UNKNOWN").length,
  };

  return (
    <div className="breakdown">
      <div className={`verdict-panel verdict-panel--${verdict.tone}`}>
        <div className="verdict-panel__top">
          <VerdictBadge state={eligibility.eligibility_state} />
          {rows.length > 0 && (
            <p className="verdict-panel__counts">
              {counts.PASS} passed · {counts.FAIL} failed · {counts.UNKNOWN} not verified
            </p>
          )}
        </div>
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
              <li key={`${row.requirement_type}-${index}`} className={`requirement requirement--${status.tone}`}>
                <span className={`status-dot status-dot--${status.tone}`} aria-hidden="true">
                  {STATUS_GLYPH[row.status]}
                </span>
                <div className="requirement__body">
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
                  {reason && (
                    <p className="requirement__review">
                      <strong>Why this needs your attention: </strong>
                      {reason}
                    </p>
                  )}
                  <div className="requirement__tags">
                    <Badge tone={row.method === "ai_reasoning" ? "warning" : "neutral"}>
                      {row.method === "ai_reasoning" ? <SparkIcon size={12} /> : <RuleIcon size={12} />}
                      {METHOD_LABEL[row.method]}
                    </Badge>
                    <Badge tone={row.provenance === "PROSE_DERIVED" ? "warning" : "neutral"}>
                      <DocumentIcon size={12} />
                      {PROVENANCE_LABEL[row.provenance]}
                    </Badge>
                    <Badge>{CONFIDENCE_LABEL[row.confidence]}</Badge>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
