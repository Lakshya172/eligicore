import { ArrowRightIcon, CheckIcon, InfoIcon, QuestionIcon, RuleIcon, ShieldIcon, SparkIcon } from "../components/icons";
import { VerdictBadge } from "../components/ui";
import { Link } from "../router";

const STEPS = [
  {
    title: "Add your profile",
    text: "Enter your degree, graduation year, grade and backlogs, or upload a résumé to pre-fill them. It stays in your browser tab.",
  },
  {
    title: "Explore opportunities",
    text: "Browse the supported catalogue of internships and graduate roles, with the requirements each employer states.",
  },
  {
    title: "See exactly why",
    text: "Every verdict comes with a requirement-by-requirement explanation, so you know where you stand before you apply.",
  },
];

/** A static illustration built from the real components. It shows no catalogue data. */
function ProductPreview() {
  const rows = [
    { icon: <CheckIcon size={14} />, tone: "success", label: "Minimum grade 7.0 out of 10", value: "Yours: 8.2", status: "Pass" },
    { icon: <CheckIcon size={14} />, tone: "success", label: "Graduation year 2026 – 2027", value: "Yours: 2027", status: "Pass" },
    { icon: <QuestionIcon size={14} />, tone: "neutral", label: "Field of study", value: "Not an exact match", status: "Not verified" },
  ] as const;
  return (
    <figure className="preview" aria-label="Illustration of an eligibility explanation">
      <div className="preview__window">
        <div className="preview__chrome" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <div className="preview__body">
          <div className="preview__head">
            <span className="preview__logo" aria-hidden="true">E</span>
            <div>
              <p className="preview__title">Software Engineering Intern</p>
              <p className="preview__company">Example employer · Internship</p>
            </div>
          </div>
          <div className="preview__verdict">
            <VerdictBadge state="NEEDS_REVIEW" />
            <p>2 of 3 requirements met · 1 needs your review</p>
          </div>
          <ul className="preview__rows">
            {rows.map((row) => (
              <li key={row.label}>
                <span className={`status-dot status-dot--${row.tone}`} aria-hidden="true">
                  {row.icon}
                </span>
                <span className="preview__row-text">
                  <span>{row.label}</span>
                  <span className="preview__row-value">{row.value}</span>
                </span>
                <span className={`badge badge--${row.tone}`}>{row.status}</span>
              </li>
            ))}
          </ul>
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
          <p className="pill">
            <span className="pill__dot" aria-hidden="true" />
            Eligibility-first job discovery for students
          </p>
          <h1 className="hero__title">
            Understand your eligibility <span className="accent-text">before you apply.</span>
          </h1>
          <p className="hero__lead">
            EligiCore checks the requirements employers state — grades, graduation year, backlogs,
            qualification and field of study — against your profile, and explains every result. Spend
            your applications on roles you actually qualify for.
          </p>
          <div className="hero__actions">
            <Link to="opportunities" className="button button--primary button--lg">
              Explore opportunities
              <ArrowRightIcon />
            </Link>
            <Link to="dashboard" className="button button--secondary button--lg">
              Open dashboard
            </Link>
          </div>
          <ul className="hero__facts">
            <li>
              <CheckIcon size={14} /> No account needed
            </li>
            <li>
              <CheckIcon size={14} /> Profile never stored on a server
            </li>
            <li>
              <CheckIcon size={14} /> Never applies for you
            </li>
          </ul>
        </div>
        <ProductPreview />
      </section>

      <section className="section" aria-labelledby="how-heading">
        <div className="section__intro">
          <p className="eyebrow">How it works</p>
          <h2 id="how-heading" className="section-title">
            Three steps to a clear answer
          </h2>
        </div>
        <ol className="steps">
          {STEPS.map((step, index) => (
            <li key={step.title} className="card step">
              <span className="step__number" aria-hidden="true">
                {String(index + 1).padStart(2, "0")}
              </span>
              <h3 className="step__title">
                <span className="visually-hidden">Step {index + 1}: </span>
                {step.title}
              </h3>
              <p className="step__text">{step.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="section" aria-labelledby="trust-heading">
        <div className="section__intro">
          <p className="eyebrow">Built to be trusted</p>
          <h2 id="trust-heading" className="section-title">
            Honest answers, and your data stays yours
          </h2>
        </div>
        <div className="principles">
          <article className="card principle">
            <span className="principle__icon" aria-hidden="true">
              <RuleIcon size={18} />
            </span>
            <h3>Rules first, AI second</h3>
            <p>
              Grades, graduation years, backlogs and qualifications are checked by plain rules. AI is
              consulted only when a field of study is ambiguous, and it can never overrule a failed
              rule check.
            </p>
          </article>
          <article className="card principle">
            <span className="principle__icon" aria-hidden="true">
              <SparkIcon size={18} />
            </span>
            <h3>Honest about uncertainty</h3>
            <p>
              Missing information is reported as "not verified", never as a failure. When something
              needs your judgement, EligiCore says so instead of guessing.
            </p>
          </article>
          <article className="card principle">
            <span className="principle__icon" aria-hidden="true">
              <ShieldIcon size={18} />
            </span>
            <h3>Private by design</h3>
            <p>
              Your profile lives in this browser tab. It is sent only to compute a result, and the
              server keeps no profile, résumé or result.
            </p>
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
          <Link to="profile" className="button button--inverse">
            Add your profile
          </Link>
          <Link to="about" className="button button--ghost-inverse">
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
