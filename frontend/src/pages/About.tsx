import type { ReactNode } from "react";
import { DocumentIcon, QuestionIcon, RuleIcon, ShieldIcon, SparkIcon, AlertIcon } from "../components/icons";
import { Card, PageHeader, SectionHead, VerdictBadge } from "../components/ui";
import { VERDICTS, VERDICT_ORDER } from "../lib/eligibility";

const RESULT_KINDS: { icon: ReactNode; title: string; tag: string; text: string }[] = [
  {
    icon: <RuleIcon size={18} />,
    title: "Verified rule check",
    tag: "Rule check · Stated by employer",
    text: "A requirement the employer published in a structured field, compared with your value by a plain rule. A failure here is final and makes a role Not eligible.",
  },
  {
    icon: <DocumentIcon size={18} />,
    title: "Read from the job description",
    tag: "Read from job description",
    text: "A requirement found in the description's text rather than a structured field. It is shown with the sentence it came from, and a failure only ever means Needs review. This is switched off by default.",
  },
  {
    icon: <SparkIcon size={18} />,
    title: "AI-assisted judgement",
    tag: "AI-assisted judgement",
    text: "Used only to judge whether your field of study is related to a permitted one. It is never treated as a verified fact, carries at most medium confidence, and can never make you ineligible.",
  },
  {
    icon: <QuestionIcon size={18} />,
    title: "Needs your review",
    tag: "Not verified",
    text: "Something could not be checked — different grading scales, an inconclusive judgement, or a value missing from your profile. EligiCore says so instead of guessing.",
  },
  {
    icon: <AlertIcon size={18} />,
    title: "Unsupported or unavailable",
    tag: "Not evaluated",
    text: "Free-text employer notes, skills and anything outside the five requirement types are shown but never evaluated. Skills only affect relevance ranking.",
  },
];

export function About() {
  return (
    <div className="page page--narrow">
      <PageHeader eyebrow="How it works" title="How EligiCore decides">
        <p>
          EligiCore compares your profile with the requirements an employer states, and tells you which
          ones you meet, which you don't, and which it couldn't verify.
        </p>
      </PageHeader>

      <Card>
        <SectionHead title="What gets checked" />
        <ol className="flow">
          <li>
            <span className="flow__step">1</span>
            <div>
              <strong>Five requirement types.</strong> Minimum grade (only on the same grading scale),
              graduation year window, maximum backlogs, minimum qualification level and permitted
              fields of study.
            </div>
          </li>
          <li>
            <span className="flow__step">2</span>
            <div>
              <strong>Rules first.</strong> Each is checked by a plain rule. A failed rule check of a
              requirement the employer states is final.
            </div>
          </li>
          <li>
            <span className="flow__step">3</span>
            <div>
              <strong>AI only for ambiguity.</strong> When your field of study is not an exact match, an
              AI-assisted judgement may say whether the fields are related. It cannot override a failed
              rule check.
            </div>
          </li>
        </ol>
      </Card>

      <Card>
        <SectionHead title="Kinds of result">
          <p>Every requirement on a job page is labelled with one of these, so you know how far to trust it.</p>
        </SectionHead>
        <ul className="kinds">
          {RESULT_KINDS.map((kind) => (
            <li key={kind.title} className="kind">
              <span className="kind__icon" aria-hidden="true">
                {kind.icon}
              </span>
              <div>
                <p className="kind__title">
                  {kind.title} <span className="badge badge--neutral">{kind.tag}</span>
                </p>
                <p className="kind__text">{kind.text}</p>
              </div>
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <SectionHead title="What each verdict means" />
        <dl className="verdict-list">
          {VERDICT_ORDER.map((state) => (
            <div key={state} className="verdict-list__row">
              <dt>
                <VerdictBadge state={state} />
              </dt>
              <dd>{VERDICTS[state].meaning}</dd>
            </div>
          ))}
        </dl>
      </Card>

      <div className="two-up">
        <Card>
          <SectionHead title="Your data" />
          <ul className="check-list">
            <li>Your profile is kept in this browser tab only and is cleared when you close it.</li>
            <li>It is sent to the EligiCore API to compute a result. The server stores no profile, résumé or result.</li>
            <li>An uploaded résumé is deleted by the server as soon as it has been read, whether or not reading succeeds.</li>
            <li>Contact details found in a résumé are not kept by this app.</li>
          </ul>
        </Card>

        <Card>
          <SectionHead title="Limitations" />
          <ul className="check-list check-list--muted">
            <li>The opportunities shown are a curated synthetic catalogue. The employers are fictional and the application links are placeholders.</li>
            <li>Search and the eligibility filter run in your browser over the loaded catalogue.</li>
            <li>Résumé reading uses an offline pattern-based extractor in this build, so review what it fills in.</li>
            <li>EligiCore never applies for you, fills employer forms or contacts employers.</li>
          </ul>
        </Card>
      </div>

      <p className="fineprint about-footnote">
        <ShieldIcon size={14} /> EligiCore assists with discovery and eligibility. It does not guarantee
        eligibility, cover every employer, or submit applications.
      </p>
    </div>
  );
}
