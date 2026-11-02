import { useRef, useState, type FormEvent } from "react";
import { api, ApiError, describeError, MAX_RESUME_BYTES } from "../api/client";
import type { CandidateProfile, ResumeParseResponse, ValidationIssue } from "../api/types";
import { InfoIcon, ShieldIcon, UploadIcon } from "../components/icons";
import { Badge, Card, PageHeader, Spinner } from "../components/ui";
import {
  DEGREE_LEVELS,
  EMPTY_EDUCATION,
  EMPTY_FORM,
  GRADE_SCALES,
  formErrors,
  formToProfile,
  profileToForm,
  type EducationForm,
  type ProfileForm,
} from "../lib/profile";
import { SAMPLE_PROFILE } from "../lib/sampleProfile";
import { Link } from "../router";
import { useProfile } from "../state/ProfileContext";

const ACCEPTED_EXTENSIONS = [".pdf", ".docx"];

const PARSE_STATUS_LABEL: Record<ResumeParseResponse["status"], { label: string; tone: "success" | "warning" }> = {
  PARSED: { label: "Parsed", tone: "success" },
  PARTIAL: { label: "Partly parsed", tone: "warning" },
  NEEDS_REVIEW: { label: "Needs your review", tone: "warning" },
};

/** Contact details are not needed for eligibility, so they are not kept or re-sent. */
function withoutContactDetails(profile: CandidateProfile): CandidateProfile {
  const copy = { ...profile };
  delete copy.name;
  delete copy.email;
  delete copy.phone;
  delete copy.resume_raw_text;
  return copy;
}

function IssueList({ issues }: { issues: ValidationIssue[] }) {
  if (issues.length === 0) return null;
  return (
    <ul className="issues">
      {issues.map((issue, index) => (
        <li key={`${issue.field}-${issue.code}-${index}`} className={`issue issue--${issue.severity.toLowerCase()}`}>
          <span className="issue__severity">{issue.severity === "ERROR" ? "Must fix" : issue.severity === "WARNING" ? "Check" : "Note"}</span>
          {issue.message}
        </li>
      ))}
    </ul>
  );
}

type UploadState =
  | { status: "idle" }
  | { status: "processing"; fileName: string }
  | { status: "done"; result: ResumeParseResponse }
  | { status: "error"; message: string };

function ResumeUpload({ onParsed }: { onParsed: (profile: CandidateProfile) => void }) {
  const [state, setState] = useState<UploadState>({ status: "idle" });
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    const lower = file.name.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.some((extension) => lower.endsWith(extension))) {
      setState({ status: "error", message: "Only PDF and DOCX résumés are supported." });
      return;
    }
    if (file.size > MAX_RESUME_BYTES) {
      setState({ status: "error", message: "That file is larger than the 5 MB limit." });
      return;
    }
    setState({ status: "processing", fileName: file.name });
    try {
      const result = await api.parseResume(file);
      setState({ status: "done", result });
      onParsed(withoutContactDetails(result.profile));
    } catch (error) {
      setState({ status: "error", message: describeError(error) });
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <Card>
      <div className="card__eyebrow-row">
        <span className="step-badge" aria-hidden="true">1</span>
        <h2 className="card__title">Start from your résumé</h2>
        <span className="optional-tag">Optional</span>
      </div>
      <p className="muted">
        Upload a PDF or DOCX (up to 5 MB) to pre-fill the form below. The server reads it, returns the
        extracted details and deletes the file immediately, whether or not parsing succeeds.
      </p>
      <label className={`dropzone ${state.status === "processing" ? "dropzone--busy" : ""}`}>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className="visually-hidden"
          disabled={state.status === "processing"}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleFile(file);
          }}
        />
        <span className="dropzone__icon" aria-hidden="true">
          {state.status === "processing" ? <Spinner label="Processing résumé" /> : <UploadIcon size={20} />}
        </span>
        {state.status === "processing" ? (
          <span className="dropzone__text">
            <strong>Reading {state.fileName}…</strong>
            <span className="dropzone__hint">This usually takes a second. Nothing is kept afterwards.</span>
          </span>
        ) : (
          <span className="dropzone__text">
            <span>
              <strong>Choose a résumé file</strong> (PDF or DOCX)
            </span>
            <span className="dropzone__hint">Up to 5 MB · read once, then deleted by the server</span>
          </span>
        )}
      </label>
      <div aria-live="polite">
        {state.status === "error" && <p className="notice notice--danger">{state.message}</p>}
        {state.status === "done" && (
          <div className="parse-result">
            <p>
              <Badge tone={PARSE_STATUS_LABEL[state.result.status].tone}>
                {PARSE_STATUS_LABEL[state.result.status].label}
              </Badge>{" "}
              {state.result.metadata.characters_extracted.toLocaleString()} characters read from your{" "}
              {state.result.metadata.source_format}. The form below is pre-filled — review it before saving.
            </p>
            <IssueList issues={state.result.issues} />
            <p className="fineprint">
              Extracted by the <code>{state.result.metadata.provider}</code> provider. Anything your résumé
              does not state is left blank rather than guessed. Contact details are not kept.
            </p>
          </div>
        )}
      </div>
    </Card>
  );
}

function EducationFields({
  entry,
  index,
  canRemove,
  onChange,
  onRemove,
}: {
  entry: EducationForm;
  index: number;
  canRemove: boolean;
  onChange: (next: EducationForm) => void;
  onRemove: () => void;
}) {
  const id = (name: string) => `edu-${index}-${name}`;
  const update = (patch: Partial<EducationForm>) => onChange({ ...entry, ...patch });
  return (
    <fieldset className="education">
      <legend className="education__legend">
        Qualification {index + 1}
        {canRemove && (
          <button type="button" className="text-button" onClick={onRemove}>
            Remove
          </button>
        )}
      </legend>
      <div className="form-grid">
        <label className="field" htmlFor={id("degree")}>
          <span className="field__label">Degree</span>
          <input id={id("degree")} className="input" placeholder="e.g. B.Tech" value={entry.degree} maxLength={200} onChange={(e) => update({ degree: e.target.value })} />
        </label>
        <label className="field" htmlFor={id("level")}>
          <span className="field__label">Level</span>
          <select id={id("level")} className="input" value={entry.level} onChange={(e) => update({ level: e.target.value as EducationForm["level"] })}>
            {DEGREE_LEVELS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
        <label className="field" htmlFor={id("field")}>
          <span className="field__label">Field of study</span>
          <input id={id("field")} className="input" placeholder="e.g. Computer Science" value={entry.fieldOfStudy} maxLength={200} onChange={(e) => update({ fieldOfStudy: e.target.value })} />
        </label>
        <label className="field" htmlFor={id("year")}>
          <span className="field__label">Graduation year</span>
          <input id={id("year")} className="input" inputMode="numeric" placeholder="e.g. 2027" value={entry.gradYear} onChange={(e) => update({ gradYear: e.target.value })} />
        </label>
        <label className="field" htmlFor={id("cgpa")}>
          <span className="field__label">Grade (CGPA or %)</span>
          <input id={id("cgpa")} className="input" inputMode="decimal" placeholder="e.g. 8.2" value={entry.cgpa} onChange={(e) => update({ cgpa: e.target.value })} />
        </label>
        <label className="field" htmlFor={id("scale")}>
          <span className="field__label">Grading scale</span>
          <select id={id("scale")} className="input" value={entry.scale} onChange={(e) => update({ scale: e.target.value as EducationForm["scale"] })}>
            {GRADE_SCALES.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
      </div>
      {entry.cgpa.trim() !== "" && entry.scale === "UNKNOWN" && (
        <p className="field__hint">Without a grading scale your grade cannot be compared with a cutoff.</p>
      )}
    </fieldset>
  );
}

export function Profile() {
  const { profile, isSample, setProfile, clearProfile } = useProfile();
  const [form, setForm] = useState<ProfileForm>(() => (profile ? profileToForm(profile) : EMPTY_FORM));
  const [base, setBase] = useState<CandidateProfile>(() => (profile && !isSample ? profile : {}));
  const [errors, setErrors] = useState<string[]>([]);
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  function updateEducation(index: number, next: EducationForm) {
    setForm((current) => ({
      ...current,
      education: current.education.map((entry, i) => (i === index ? next : entry)),
    }));
    setSaved(false);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaved(false);
    const problems = formErrors(form);
    setErrors(problems);
    setIssues([]);
    if (problems.length > 0) return;

    setSaving(true);
    try {
      const candidate = formToProfile(form, base);
      const validation = await api.validateProfile(candidate);
      setIssues(validation.issues);
      if (!validation.is_valid) return;
      setProfile(validation.profile, { isSample: false });
      setBase(validation.profile);
      setSaved(true);
    } catch (error) {
      if (error instanceof ApiError && error.details.length > 0) {
        setErrors(error.details.map((detail) => `${detail.field}: ${detail.message}`));
      } else {
        setErrors([describeError(error)]);
      }
    } finally {
      setSaving(false);
    }
  }

  function applySample() {
    setProfile(SAMPLE_PROFILE, { isSample: true });
    setForm(profileToForm(SAMPLE_PROFILE));
    setBase({});
    setErrors([]);
    setIssues([]);
    setSaved(false);
  }

  function clearAll() {
    clearProfile();
    setForm(EMPTY_FORM);
    setBase({});
    setErrors([]);
    setIssues([]);
    setSaved(false);
  }

  return (
    <div className="page page--narrow">
      <PageHeader
        eyebrow="Profile"
        title="Your eligibility profile"
        actions={
          <>
            <button type="button" className="button button--secondary" onClick={applySample}>
              Use sample profile
            </button>
            {profile && (
              <button type="button" className="button button--ghost" onClick={clearAll}>
                Clear
              </button>
            )}
          </>
        }
      >
        <p>
          These are the details employers set requirements on. They stay in this browser tab and are sent
          only to evaluate your eligibility — EligiCore's server stores none of it.
        </p>
      </PageHeader>

      {isSample && (
        <p className="notice notice--warning">
          <InfoIcon />
          <span>
            You're viewing the <strong>sample profile</strong> — a fictional student for demonstration. Edit
            and save it to make it your own, or clear it.
          </span>
        </p>
      )}

      <aside className="privacy-panel" aria-label="How your information is handled">
        <span className="privacy-panel__icon" aria-hidden="true">
          <ShieldIcon size={18} />
        </span>
        <ul>
          <li>Your profile is kept only in this browser tab and cleared when you close it.</li>
          <li>A résumé is read once to pre-fill this form; the server deletes it straight away.</li>
          <li>There is no account and no stored profile — nothing here is saved on a server.</li>
          <li>The sample profile is a fictional student, for demonstrations only.</li>
        </ul>
      </aside>

      <ResumeUpload
        onParsed={(parsed) => {
          setForm(profileToForm(parsed));
          setBase(parsed);
          setErrors([]);
          setIssues([]);
          setSaved(false);
        }}
      />

      <form className="card profile-form" onSubmit={handleSubmit} noValidate>
        <div className="card__eyebrow-row">
          <span className="step-badge" aria-hidden="true">2</span>
          <h2 className="card__title">Education</h2>
        </div>
        <p className="muted form-intro">
          Check every value. Anything left blank stays "not stated" — it is never treated as zero.
        </p>
        {form.education.map((entry, index) => (
          <EducationFields
            key={index}
            entry={entry}
            index={index}
            canRemove={form.education.length > 1}
            onChange={(next) => updateEducation(index, next)}
            onRemove={() =>
              setForm((current) => ({ ...current, education: current.education.filter((_, i) => i !== index) }))
            }
          />
        ))}
        <button
          type="button"
          className="button button--ghost button--sm"
          onClick={() => setForm((current) => ({ ...current, education: [...current.education, { ...EMPTY_EDUCATION }] }))}
          disabled={form.education.length >= 20}
        >
          + Add another qualification
        </button>

        <h2 className="card__title card__title--spaced">Academic record</h2>
        <div className="form-grid">
          <label className="field" htmlFor="backlogs">
            <span className="field__label">Active backlogs</span>
            <input
              id="backlogs"
              className="input"
              inputMode="numeric"
              placeholder="Leave blank if not stated"
              value={form.backlogs}
              onChange={(e) => {
                setForm({ ...form, backlogs: e.target.value });
                setSaved(false);
              }}
            />
            <span className="field__hint">Blank means "not stated", which is different from zero.</span>
          </label>
        </div>

        <h2 className="card__title card__title--spaced">Skills and preferences</h2>
        <label className="field" htmlFor="skills">
          <span className="field__label">Skills</span>
          <textarea
            id="skills"
            className="input input--textarea"
            placeholder="Python, SQL, Git"
            value={form.skills}
            onChange={(e) => {
              setForm({ ...form, skills: e.target.value });
              setSaved(false);
            }}
          />
          <span className="field__hint">Separate with commas. Skills affect relevance ranking, never eligibility.</span>
        </label>
        <fieldset className="checkbox-group">
          <legend className="field__label">Interested in</legend>
          {(["INTERNSHIP", "FULL_TIME"] as const).map((type) => (
            <label key={type} className="checkbox">
              <input
                type="checkbox"
                checked={form.jobTypes.includes(type)}
                onChange={(e) => {
                  setForm({
                    ...form,
                    jobTypes: e.target.checked ? [...form.jobTypes, type] : form.jobTypes.filter((t) => t !== type),
                  });
                  setSaved(false);
                }}
              />
              {type === "INTERNSHIP" ? "Internships" : "Full-time roles"}
            </label>
          ))}
        </fieldset>

        <div aria-live="polite">
          {errors.length > 0 && (
            <div className="notice notice--danger" role="alert">
              <p><strong>Please fix the following:</strong></p>
              <ul>
                {errors.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            </div>
          )}
          <IssueList issues={issues} />
          {saved && (
            <p className="notice notice--success">
              Profile saved in this tab. <Link to="opportunities">Explore opportunities</Link> or{" "}
              <Link to="dashboard">see your dashboard</Link>.
            </p>
          )}
        </div>

        <div className="form-actions">
          <button type="submit" className="button button--primary" disabled={saving}>
            {saving ? "Saving…" : "Save and check eligibility"}
          </button>
        </div>
      </form>
    </div>
  );
}
