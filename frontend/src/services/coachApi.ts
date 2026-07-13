/**
 * Thin fetch wrapper over the `/coach/*` Career Coach API (Phase 57, ADR-0075).
 * Unlike `api.ts`, every call here is a POST -- each Career Coach endpoint
 * is a stateless, self-contained request (resume/JD text in the body),
 * never a mutation to stored data. See `hooks/useCoach.ts` for the
 * TanStack Query `useMutation` wrappers that call these.
 */

import { apiFetchJson } from "./http";
import type {
  CoverLetterMode,
  CoverLetterTransformResult,
  InterviewPrepResult,
  JobMatchResult,
  ProfileMatchResult,
  ResumeAnalysis,
  ResumeSuggestion,
  SkillGapReport,
} from "@/types/api";

function postJson<T>(path: string, body: unknown): Promise<T> {
  return apiFetchJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const coachApi = {
  resumeAnalysis: (resume_text: string, jd_text: string) =>
    postJson<ResumeAnalysis>("/coach/resume-analysis", { resume_text, jd_text }),
  jobMatch: (resume_text: string, jd_text: string) =>
    postJson<JobMatchResult>("/coach/job-match", { resume_text, jd_text }),
  skillGap: (resume_text: string, jd_text: string) =>
    postJson<SkillGapReport>("/coach/skill-gap", { resume_text, jd_text }),
  resumeSuggestions: (resume_text: string, jd_text: string) =>
    postJson<ResumeSuggestion[]>("/coach/resume-suggestions", { resume_text, jd_text }),
  coverLetterTransform: (body: string, mode: CoverLetterMode) =>
    postJson<CoverLetterTransformResult>("/coach/cover-letter/transform", { body, mode }),
  interviewPrep: (jd_text: string) =>
    postJson<InterviewPrepResult>("/coach/interview-prep", { jd_text }),
  profileMatch: (jd_text: string) =>
    postJson<ProfileMatchResult>("/coach/profile-match", { jd_text }),
};
