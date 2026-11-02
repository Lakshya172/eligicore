import { describe, expect, it } from "vitest";
import {
  EMPTY_EDUCATION,
  EMPTY_FORM,
  formErrors,
  formToProfile,
  hasEvaluableData,
  parseList,
  profileToForm,
  withoutResumeText,
  type ProfileForm,
} from "./profile";

const filled: ProfileForm = {
  education: [
    {
      ...EMPTY_EDUCATION,
      degree: " B.Tech ",
      level: "BACHELORS",
      fieldOfStudy: "Information Technology",
      gradYear: "2027",
      cgpa: "8.2",
      scale: "SCALE_10",
    },
  ],
  backlogs: "0",
  skills: "Python, SQL,\npython ,  Git",
  jobTypes: ["INTERNSHIP"],
};

describe("formToProfile", () => {
  it("builds the API profile from the form", () => {
    expect(formToProfile(filled)).toEqual({
      education: [
        {
          degree: "B.Tech",
          level: "BACHELORS",
          field_of_study: "Information Technology",
          institution: null,
          grad_year: 2027,
          cgpa: 8.2,
          scale: "SCALE_10",
        },
      ],
      backlogs: 0,
      skills: ["Python", "SQL", "Git"],
      preferences: { job_types: ["INTERNSHIP"] },
    });
  });

  it("keeps an unstated backlog count as null, never zero", () => {
    expect(formToProfile({ ...filled, backlogs: "" }).backlogs).toBeNull();
    expect(formToProfile({ ...filled, backlogs: "   " }).backlogs).toBeNull();
  });

  it("keeps an unknown grading scale unknown and a blank grade absent", () => {
    const [entry] = formToProfile({
      ...filled,
      education: [{ ...filled.education[0]!, cgpa: "", scale: "UNKNOWN" }],
    }).education!;
    expect(entry!.cgpa).toBeNull();
    expect(entry!.scale).toBe("UNKNOWN");
  });

  it("drops qualifications without a degree name instead of inventing one", () => {
    expect(formToProfile(EMPTY_FORM).education).toEqual([]);
  });

  it("preserves profile data the form does not edit", () => {
    const base = { experience: [{ title: "Intern" }], preferences: { work_mode: "REMOTE" as const } };
    const profile = formToProfile(filled, base);
    expect(profile.experience).toEqual([{ title: "Intern" }]);
    expect(profile.preferences).toEqual({ work_mode: "REMOTE", job_types: ["INTERNSHIP"] });
  });
});

describe("formErrors", () => {
  it("accepts a complete form", () => {
    expect(formErrors(filled)).toEqual([]);
  });

  it("rejects values the API would reject", () => {
    const errors = formErrors({
      ...filled,
      education: [{ ...filled.education[0]!, gradYear: "20255", cgpa: "-1" }],
      backlogs: "two",
    });
    expect(errors).toHaveLength(3);
  });

  it("asks for a degree name once other qualification details are entered", () => {
    const errors = formErrors({ ...EMPTY_FORM, education: [{ ...EMPTY_EDUCATION, gradYear: "2027" }] });
    expect(errors[0]).toMatch(/degree name/);
  });
});

describe("profile helpers", () => {
  it("round-trips through the form", () => {
    expect(profileToForm(formToProfile(filled))).toEqual({
      ...filled,
      education: [{ ...filled.education[0]!, degree: "B.Tech" }],
      skills: "Python, SQL, Git",
    });
  });

  it("splits lists without duplicates", () => {
    expect(parseList("a, b,, A , c\nb")).toEqual(["a", "b", "c"]);
  });

  it("never keeps raw résumé text", () => {
    expect(withoutResumeText({ resume_raw_text: "secret", skills: ["x"] })).toEqual({ skills: ["x"] });
  });

  it("knows when there is something to evaluate", () => {
    expect(hasEvaluableData(null)).toBe(false);
    expect(hasEvaluableData({})).toBe(false);
    expect(hasEvaluableData({ backlogs: 0 })).toBe(true);
  });
});
