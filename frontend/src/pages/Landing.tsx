import { Link } from "../router";

const STEPS = [
  {
    title: "Add your profile",
    text: "Enter your degree, graduation year, grade and backlogs, or upload a résumé to pre-fill them. It stays in your browser.",
  },
  {
    title: "Explore opportunities",
    text: "Browse internships and graduate roles with the requirements each employer actually states.",
  },
  {
    title: "See exactly why",
    text: "Every verdict comes with a requirement-by-requirement explanation, so you know where you stand and what to check.",
  },
];

const VERDICT_PREVIEW = [
  { tone: "success", label: "Eligible", text: "Minimum grade 7.0 out of 10 — yours: 8.2" },
  { tone: "warning", label: "Needs review", text: "Field of study is not an exact match" },
  { tone: "danger", label: "Not eligible", text: "Graduation year window 2024 – 2026" },
] as const;

export function Landing() {
  return (
    <div className="landing">
      <section className="hero">
        <div className="hero__copy">
          <p className="eyebrow">Eligibility-first job discovery</p>
          <h1 className="hero__title">
            Know which roles you can <span className="accent-text">actually</span> apply for.
          </h1>
          <p className="hero__lead">
            Most job tools tell you how well you fit. EligiCore answers the question that comes
            first: do you meet the requirements, and why?
          </p>
          <div className="hero__actions">
            <Link to="opportunities" className="button button--primary button--lg">
              Explore opportunities
            </Link>
            <Link to="dashboard" className="button button--secondary button--lg">
              Open dashboard
            </Link>
          </div>
          <p className="hero__fineprint">
            No account needed. Your profile is never stored on a server.
          </p>
        </div>
        <div className="hero__visual" aria-hidden="true">
          <div className="preview-card">
            <div className="preview-card__head">
              <span className="preview-card__logo">A</span>
              <div>
                <p className="preview-card__title">Software Engineering Intern</p>
                <p className="preview-card__company">Example Analytics · Bengaluru</p>
              </div>
            </div>
            <ul className="preview-card__rows">
              {VERDICT_PREVIEW.map((row) => (
                <li key={row.label}>
                  <span className={`verdict verdict--${row.tone}`}>
                    <span className="verdict__dot" />
                    {row.label}
                  </span>
                  <span className="preview-card__text">{row.text}</span>
                </li>
              ))}
            </ul>
            <p className="preview-card__caption">Illustration, not a real evaluation</p>
          </div>
        </div>
      </section>

      <section className="steps" aria-labelledby="how-heading">
        <h2 id="how-heading" className="section-title">
          How EligiCore works
        </h2>
        <ol className="steps__list">
          {STEPS.map((step, index) => (
            <li key={step.title} className="card step">
              <span className="step__number">{index + 1}</span>
              <h3 className="step__title">{step.title}</h3>
              <p className="step__text">{step.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="principles">
        <div className="card principle">
          <h3>Rules first, AI second</h3>
          <p>
            Grades, graduation years, backlogs and qualifications are checked by plain rules. AI
            is only consulted when a field of study is ambiguous, and it can never overrule a
            failed rule check.
          </p>
        </div>
        <div className="card principle">
          <h3>Honest about uncertainty</h3>
          <p>
            Missing information is reported as "not verified", never as a failure. When something
            needs your judgement, EligiCore says so instead of guessing.
          </p>
        </div>
        <div className="card principle principle--highlight">
          <h3>You stay in control</h3>
          <p>
            EligiCore helps you discover and assess roles. It never submits an application, fills
            an employer's form or contacts anyone for you.
          </p>
        </div>
      </section>
    </div>
  );
}
