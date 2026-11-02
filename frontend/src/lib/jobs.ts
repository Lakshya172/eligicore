import type { DegreeLevel, JobRead, JobType } from "../api/types";

export const JOB_TYPE_LABEL: Record<JobType, string> = {
  INTERNSHIP: "Internship",
  FULL_TIME: "Full-time",
  UNKNOWN: "Type not stated",
};

const DEGREE_LABEL: Record<DegreeLevel, string> = {
  HIGH_SCHOOL: "High school",
  DIPLOMA: "Diploma",
  BACHELORS: "Bachelor's degree",
  MASTERS: "Master's degree",
  DOCTORATE: "Doctorate",
  OTHER: "Other qualification",
  UNKNOWN: "Not stated",
};

const SCALE_LABEL: Record<string, string> = {
  SCALE_10: "out of 10",
  SCALE_4: "out of 4",
  SCALE_5: "out of 5",
  PERCENTAGE: "%",
};

/** Client-side search over fields the catalogue actually returns. */
export function matchesSearch(job: JobRead, query: string): boolean {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return true;
  const haystack = [job.role_title, job.company_name, job.location ?? "", ...job.required_skills]
    .join(" ")
    .toLowerCase();
  return terms.every((term) => haystack.includes(term));
}

export interface StatedRequirement {
  label: string;
  value: string;
}

/**
 * The eligibility requirements a job states in structured fields — the same five the
 * engine evaluates. Skills are listed separately because they affect matching, not
 * eligibility.
 */
export function statedRequirements(job: JobRead): StatedRequirement[] {
  const out: StatedRequirement[] = [];
  if (job.min_cgpa != null) {
    const scale = job.min_cgpa_scale ? SCALE_LABEL[job.min_cgpa_scale] ?? job.min_cgpa_scale : "scale not stated";
    const value = job.min_cgpa_scale === "PERCENTAGE" ? `${job.min_cgpa}%` : `${job.min_cgpa} ${scale}`;
    out.push({ label: "Minimum grade", value });
  }
  if (job.min_grad_year != null || job.max_grad_year != null) {
    const value =
      job.min_grad_year != null && job.max_grad_year != null
        ? job.min_grad_year === job.max_grad_year
          ? `${job.min_grad_year}`
          : `${job.min_grad_year} – ${job.max_grad_year}`
        : job.min_grad_year != null
          ? `${job.min_grad_year} or later`
          : `${job.max_grad_year} or earlier`;
    out.push({ label: "Graduation year", value });
  }
  if (job.max_backlogs != null) {
    out.push({
      label: "Backlogs",
      value: job.max_backlogs === 0 ? "None allowed" : `At most ${job.max_backlogs}`,
    });
  }
  if (job.min_degree_level != null) {
    out.push({ label: "Minimum qualification", value: DEGREE_LABEL[job.min_degree_level] });
  }
  if (job.allowed_fields.length > 0) {
    out.push({ label: "Fields of study", value: job.allowed_fields.join(", ") });
  }
  return out;
}

/** The employer's free-text notes, which the engine does not evaluate. */
export function employerNotes(job: JobRead): string | null {
  const notes = job.requirements["notes"];
  return typeof notes === "string" && notes.trim() !== "" ? notes : null;
}

export function formatDate(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(`${value.length === 10 ? `${value}T00:00:00` : value}`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** Only http(s) links are rendered as links; anything else is shown as text. */
export function safeExternalUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch {
    return null;
  }
}
