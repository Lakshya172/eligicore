import { Card, PageHeader, VerdictBadge } from "../components/ui";
import { VERDICTS, VERDICT_ORDER } from "../lib/eligibility";

export function About() {
  return (
    <div className="page page--narrow">
      <PageHeader eyebrow="How it works" title="How EligiCore decides">
        <p>
          EligiCore compares your profile with the requirements an employer states, and tells you
          which ones you meet, which you don't, and which it couldn't verify.
        </p>
      </PageHeader>

      <Card>
        <h2 className="card__title">What gets checked</h2>
        <p>
          Five kinds of requirement: minimum grade (only on the same grading scale), graduation year
          window, maximum backlogs, minimum qualification level and permitted fields of study. Each is
          checked by a plain rule first.
        </p>
        <p>
          AI is used for one narrow question: when your field of study is not an exact match for a
          permitted field, it judges whether the two are related. Those results are labelled{" "}
          <strong>AI-assisted judgement</strong>, carry at most medium confidence, and can never make you
          ineligible. A failed rule check is final, and AI cannot override it.
        </p>
      </Card>

      <Card>
        <h2 className="card__title">What each verdict means</h2>
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
        <p className="fineprint">
          A requirement read from a job's description, rather than a structured field, is labelled{" "}
          <strong>Read from job description</strong>. If it fails, the job is marked "Needs review", never
          "Not eligible". (Reading requirements from descriptions is switched off by default.)
        </p>
      </Card>

      <Card>
        <h2 className="card__title">Your data</h2>
        <ul className="plain-list">
          <li>Your profile is kept in this browser tab only and is cleared when you close it.</li>
          <li>It is sent to the EligiCore API to compute a result. The server stores no profile, résumé or result.</li>
          <li>An uploaded résumé is deleted by the server as soon as it has been read, whether or not reading succeeds.</li>
          <li>Contact details found in a résumé are not kept by this app.</li>
        </ul>
      </Card>

      <Card>
        <h2 className="card__title">Limitations</h2>
        <ul className="plain-list">
          <li>The opportunities shown are a curated synthetic catalogue. The employers are fictional and the application links are placeholders.</li>
          <li>Search and the eligibility filter run in your browser over the loaded catalogue.</li>
          <li>Résumé reading uses an offline pattern-based extractor in this build, so review what it fills in.</li>
          <li>EligiCore never applies for you, fills employer forms or contacts employers.</li>
        </ul>
      </Card>
    </div>
  );
}
