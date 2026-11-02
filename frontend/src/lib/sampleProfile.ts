import type { CandidateProfile } from "../api/types";

/**
 * A fictional student, for demonstrating the real evaluation flow. Every value is invented.
 * The UI labels it as a sample wherever it is in use, so a result computed from it is never
 * presented as a real student's evaluation.
 */
export const SAMPLE_PROFILE: CandidateProfile = {
  candidate_id: "sample-student",
  education: [
    {
      degree: "B.Tech",
      level: "BACHELORS",
      field_of_study: "Information Technology",
      institution: "Sample Institute of Technology",
      grad_year: 2027,
      cgpa: 8.2,
      scale: "SCALE_10",
    },
  ],
  backlogs: 0,
  skills: ["Python", "SQL", "Git", "Docker", "React"],
  experience: [
    {
      title: "Data Engineering Intern",
      description: "Built ingestion pipelines and internal APIs.",
    },
  ],
  preferences: { job_types: ["INTERNSHIP"] },
};
