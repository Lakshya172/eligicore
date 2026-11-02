import {
  ArrowRightIcon,
  CheckIcon,
  CompassIcon,
  DocumentIcon,
  ExternalIcon,
  InfoIcon,
  QuestionIcon,
  RuleIcon,
  ShieldIcon,
  SparkIcon,
  UserIcon,
} from "../components/icons";
import { VerdictBadge } from "../components/ui";
import { Link } from "../router";

/** The product's real workflow, in order. Each step names only what the app does today. */
const WORKFLOW = [
  {
    icon: <UserIcon />,
    title: "Build your profile",
    text: "Enter your degree, graduation year, grade and backlogs, or upload a PDF or DOCX résumé to pre-fill them. It stays in this tab.",
  },
  {
    icon: <CompassIcon />,
    title: "Discover opportunities",
    text: "Browse the supported catalogue of internships and graduate roles, and filter by type, status and verdict.",
  },
  {
    icon: <RuleIcon />,
    title: "Review the evidence",
    text: "Every stated requirement is shown as passed, failed or not verified, with where it came from.",
  },
  {
    icon: <QuestionIcon />,
    title: "Prepare",
    text: "See exactly what needs your attention, such as a missing value, a different grading scale or an ambiguous field, before you apply.",
  },
  {
    icon: <ExternalIcon />,
    title: "Apply yourself",
    text: "Open the employer's own page when you are ready. EligiCore never submits, fills a form or contacts anyone for you.",
  },
];

/** A static illustration built from the real components. It shows no catalogue data. */
function ProductPreview() {
  const rows = [
    { icon: <CheckIcon size={13} />, tone: "success", label: "Minimum grade 7.0 out of 10", value: "8.2", status: "Passed" },
    { icon: <CheckIcon size={13} />, tone: "success", label: "Graduation year 2026 – 2027", value: "2027", status: "Passed" },
    { icon: <QuestionIcon size={13} />, tone: "neutral", label: "Field of study", value: "Information Technology", status: "Not verified" },
  ] as const;
  return (
    <figure className="preview" aria-label="Illustration of an eligibility explanation">
      {/* The callout follows the window in normal flow, so it never covers a row or the caption. */}
      <div className="preview__stage">
        <div className="preview__window">
          <div className="preview__bar" aria-hidden="true">
            <span className="preview__crumb">Opportunities</span>
            <span className="preview__crumb-sep">/</span>
            <span>Eligibility</span>
            <span className="preview__counts">2 passed · 0 failed · 1 not verified</span>
          </div>
          <div className="preview__body">
            <div className="preview__head">
              <span className="preview__logo" aria-hidden="true">E</span>
              <div>
                <p className="preview__title">Software Engineering Intern</p>
                <p className="preview__company">Example employer · Internship</p>
              </div>
              <VerdictBadge state="NEEDS_REVIEW" />
            </div>
            <ul className="preview__rows">
              {rows.map((row) => (
                <li key={row.label} className={`preview__row preview__row--${row.tone}`}>
                  <span className={`status-dot status-dot--${row.tone}`} aria-hidden="true">
                    {row.icon}
                  </span>
                  <span className="preview__row-text">
                    <span>{row.label}</span>
                    <span className="preview__row-value">
                      Your profile: <code>{row.value}</code>
                    </span>
                  </span>
                  <span className={`badge badge--${row.tone}`}>{row.status}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <div className="preview__evidence" aria-hidden="true">
          <span className="preview__evidence-label">
            <DocumentIcon size={12} /> Read from the job description
          </span>
          “Open to students of Computer Science or a related field.”
        </div>
      </div>
      <figcaption className="preview__caption">Illustration, not a real evaluation</figcaption>
    </figure>
  );
}

export function Landing() {
  return (
    <div className="landing">
      <section className="hero">
        <div className="hero__copy">
          <p className="kicker">
            <span className="kicker__rule" aria-hidden="true" />
            Eligibility-first job discovery
          </p>
          <h1 className="hero__title">
            Know where you stand.
            <span className="hero__title-accent">Before you apply.</span>
          </h1>
          <p className="hero__lead">
            EligiCore helps students understand opportunity requirements, evaluate eligibility, and
            prepare with clarity.
          </p>
          <div className="hero__actions">
            <Link to="profile" className="button button--primary button--lg">
              Check your eligibility
              <ArrowRightIcon />
            </Link>
            <Link to="opportunities" className="button button--secondary button--lg">
              Browse opportunities
            </Link>
          </div>
          <ul className="hero__facts">
            <li>
              <CheckIcon size={13} /> No account needed
            </li>
            <li>
              <CheckIcon size={13} /> Profile never stored on a server
            </li>
            <li>
              <CheckIcon size={13} /> Never applies for you
            </li>
          </ul>
        </div>
        <ProductPreview />
      </section>

      <section className="checks-strip" aria-label="What EligiCore checks">
        <p className="checks-strip__label">Checked against what employers state</p>
        <ul>
          <li>Minimum grade</li>
          <li>Graduation year</li>
          <li>Backlogs</li>
          <li>Qualification level</li>
          <li>Field of study</li>
        </ul>
      </section>

      <section className="section" aria-labelledby="how-heading">
        <div className="section__intro section__intro--left">
          <p className="eyebrow">How it works</p>
          <h2 id="how-heading" className="section-title">
            From profile to application, in five steps.
          </h2>
          <p className="section__lead">You decide at every step. The last one is always yours.</p>
        </div>
        <ol className="workflow">
          {WORKFLOW.map((step, index) => (
            <li key={step.title} className={`workflow__step ${index === WORKFLOW.length - 1 ? "workflow__step--yours" : ""}`}>
              <div className="workflow__marker" aria-hidden="true">
                <span className="workflow__icon">{step.icon}</span>
                <span className="workflow__number">{String(index + 1).padStart(2, "0")}</span>
              </div>
              <h3 className="workflow__title">
                <span className="visually-hidden">Step {index + 1}: </span>
                {step.title}
              </h3>
              <p className="workflow__text">{step.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="section section--split" aria-labelledby="trust-heading">
        <div className="section__intro section__intro--left section__intro--sticky">
          <p className="eyebrow">Built to be trusted</p>
          <h2 id="trust-heading" className="section-title">
            Honest answers.
            <br />
            Your data stays yours.
          </h2>
          <p className="section__lead">
            EligiCore separates what it verified from what it could not, and it never keeps your
            profile.
          </p>
        </div>
        <div className="principles">
          <article className="principle">
            <span className="principle__icon" aria-hidden="true">
              <RuleIcon size={18} />
            </span>
            <div>
              <h3>Rules first, AI second</h3>
              <p>
                Grades, graduation years, backlogs and qualifications are checked by plain rules. AI
                is consulted only when a field of study is ambiguous, and it can never overrule a
                failed rule check.
              </p>
            </div>
          </article>
          <article className="principle">
            <span className="principle__icon" aria-hidden="true">
              <SparkIcon size={18} />
            </span>
            <div>
              <h3>Honest about uncertainty</h3>
              <p>
                Missing information is reported as "not verified", never as a failure. When something
                needs your judgement, EligiCore says so instead of guessing.
              </p>
            </div>
          </article>
          <article className="principle">
            <span className="principle__icon" aria-hidden="true">
              <ShieldIcon size={18} />
            </span>
            <div>
              <h3>Private by design</h3>
              <p>
                Your profile lives in this browser tab. It is sent only to compute a result, and the
                server keeps no profile, résumé or result.
              </p>
            </div>
          </article>
        </div>
      </section>

      <section className="cta-band">
        <div>
          <h2 className="cta-band__title">You stay in control of every application.</h2>
          <p className="cta-band__text">
            EligiCore helps you discover and assess roles. It never submits an application, fills an
            employer's form or contacts anyone for you.
          </p>
        </div>
        <div className="cta-band__actions">
          <Link to="profile" className="button button--primary">
            Add your profile
          </Link>
          <Link to="about" className="button button--secondary">
            How EligiCore decides
          </Link>
        </div>
        <p className="cta-band__note">
          <InfoIcon size={14} /> The opportunities in this build are a synthetic demo catalogue with
          fictional employers.
        </p>
      </section>
    </div>
  );
}
