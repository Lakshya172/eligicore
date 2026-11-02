// Converts between the profile form and the API's CandidateProfile. The rules here are the
// backend's honesty rules applied in the browser: a blank value stays absent, an unknown
// scale stays UNKNOWN, and an unstated backlog count stays null rather than becoming 0.

import type {
  CandidateProfile,
  DegreeLevel,
  EducationEntry,
  GradeScale,
  PreferableJobType,
} from "../api/types";

export interface EducationForm {
  degree: string;
  level: DegreeLevel;
  fieldOfStudy: string;
  institution: string;
  gradYear: string;
  cgpa: string;
  scale: GradeScale;
}

export interface ProfileForm {
  education: EducationForm[];
  /** Empty string means "not stated". */
  backlogs: string;
  skills: string;
  jobTypes: PreferableJobType[];
}

export const EMPTY_EDUCATION: EducationForm = {
  degree: "",
  level: "UNKNOWN",
  fieldOfStudy: "",
  institution: "",
  gradYear: "",
  cgpa: "",
  scale: "UNKNOWN",
};

export const EMPTY_FORM: ProfileForm = {
  education: [{ ...EMPTY_EDUCATION }],
  backlogs: "",
  skills: "",
  jobTypes: [],
};

export const DEGREE_LEVELS: { value: DegreeLevel; label: string }[] = [
  { value: "UNKNOWN", label: "Not stated" },
  { value: "HIGH_SCHOOL", label: "High school" },
  { value: "DIPLOMA", label: "Diploma" },
  { value: "BACHELORS", label: "Bachelor's" },
  { value: "MASTERS", label: "Master's" },
  { value: "DOCTORATE", label: "Doctorate" },
  { value: "OTHER", label: "Other" },
];

export const GRADE_SCALES: { value: GradeScale; label: string }[] = [
  { value: "UNKNOWN", label: "Not stated" },
  { value: "SCALE_10", label: "Out of 10" },
  { value: "SCALE_4", label: "Out of 4" },
  { value: "SCALE_5", label: "Out of 5" },
  { value: "PERCENTAGE", label: "Percentage" },
];

function text(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function wholeNumber(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  return Number.parseInt(trimmed, 10);
}

function decimal(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

/** Split a comma- or newline-separated list, trimming and dropping repeats (case-insensitive). */
export function parseList(value: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of value.split(/[,\n]/)) {
    const item = raw.trim();
    const key = item.toLowerCase();
    if (item && !seen.has(key)) {
      seen.add(key);
      out.push(item);
    }
  }
  return out;
}

/** Problems the form can catch before anything is sent. The API validates again. */
export function formErrors(form: ProfileForm): string[] {
  const errors: string[] = [];
  form.education.forEach((entry, index) => {
    const position = form.education.length > 1 ? ` ${index + 1}` : "";
    const hasAnyValue =
      entry.fieldOfStudy.trim() || entry.gradYear.trim() || entry.cgpa.trim() || entry.institution.trim();
    if (!entry.degree.trim() && hasAnyValue) {
      errors.push(`Qualification${position}: add the degree name, e.g. "B.Tech".`);
    }
    if (entry.gradYear.trim()) {
      const year = wholeNumber(entry.gradYear);
      if (year === null || year < 1950 || year > 2100) {
        errors.push(`Qualification${position}: graduation year must be between 1950 and 2100.`);
      }
    }
    if (entry.cgpa.trim() && decimal(entry.cgpa) === null) {
      errors.push(`Qualification${position}: grade must be a number of zero or more.`);
    }
  });
  if (form.backlogs.trim() && wholeNumber(form.backlogs) === null) {
    errors.push("Backlogs must be a whole number, or left blank if not stated.");
  }
  return errors;
}

/** Build the API profile. Call formErrors first; invalid values are dropped, not guessed. */
export function formToProfile(form: ProfileForm, base: CandidateProfile = {}): CandidateProfile {
  const education: EducationEntry[] = form.education
    .filter((entry) => entry.degree.trim() !== "")
    .map((entry) => ({
      degree: entry.degree.trim(),
      level: entry.level,
      field_of_study: text(entry.fieldOfStudy),
      institution: text(entry.institution),
      grad_year: wholeNumber(entry.gradYear),
      cgpa: decimal(entry.cgpa),
      scale: entry.scale,
    }));

  return {
    ...base,
    education,
    backlogs: wholeNumber(form.backlogs),
    skills: parseList(form.skills),
    preferences: { ...(base.preferences ?? {}), job_types: [...form.jobTypes] },
  };
}

export function profileToForm(profile: CandidateProfile): ProfileForm {
  const education = (profile.education ?? []).map<EducationForm>((entry) => ({
    degree: entry.degree ?? "",
    level: entry.level ?? "UNKNOWN",
    fieldOfStudy: entry.field_of_study ?? "",
    institution: entry.institution ?? "",
    gradYear: entry.grad_year == null ? "" : String(entry.grad_year),
    cgpa: entry.cgpa == null ? "" : String(entry.cgpa),
    scale: entry.scale ?? "UNKNOWN",
  }));
  return {
    education: education.length > 0 ? education : [{ ...EMPTY_EDUCATION }],
    backlogs: profile.backlogs == null ? "" : String(profile.backlogs),
    skills: (profile.skills ?? []).join(", "),
    jobTypes: (profile.preferences?.job_types ?? []).filter(
      (type): type is PreferableJobType => type === "INTERNSHIP" || type === "FULL_TIME",
    ),
  };
}

/**
 * The profile as it is kept in the browser and sent for evaluation. Raw résumé text is
 * dropped: no eligibility or recommendation call needs it, so it never leaves the upload.
 */
export function withoutResumeText(profile: CandidateProfile): CandidateProfile {
  const { resume_raw_text: _dropped, ...rest } = profile;
  void _dropped;
  return rest;
}

export function hasEvaluableData(profile: CandidateProfile | null): boolean {
  if (!profile) return false;
  return (profile.education?.length ?? 0) > 0 || profile.backlogs != null || (profile.skills?.length ?? 0) > 0;
}
