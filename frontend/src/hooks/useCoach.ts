/**
 * TanStack Query `useMutation` wrappers over `coachApi` (Phase 57, ADR-0075).
 * `useMutation`, not `useQuery`: every Career Coach call is a real, costed
 * (for the LLM-backed ones) action the user explicitly triggers by
 * submitting a form -- never fetched automatically on page load.
 */

import { useMutation } from "@tanstack/react-query";
import { coachApi } from "@/services/coachApi";
import type { CoverLetterMode } from "@/types/api";

export function useResumeAnalysis() {
  return useMutation({
    mutationFn: ({ resumeText, jdText }: { resumeText: string; jdText: string }) =>
      coachApi.resumeAnalysis(resumeText, jdText),
  });
}

export function useJobMatch() {
  return useMutation({
    mutationFn: ({ resumeText, jdText }: { resumeText: string; jdText: string }) =>
      coachApi.jobMatch(resumeText, jdText),
  });
}

export function useSkillGap() {
  return useMutation({
    mutationFn: ({ resumeText, jdText }: { resumeText: string; jdText: string }) =>
      coachApi.skillGap(resumeText, jdText),
  });
}

export function useResumeSuggestions() {
  return useMutation({
    mutationFn: ({ resumeText, jdText }: { resumeText: string; jdText: string }) =>
      coachApi.resumeSuggestions(resumeText, jdText),
  });
}

export function useCoverLetterTransform() {
  return useMutation({
    mutationFn: ({ body, mode }: { body: string; mode: CoverLetterMode }) =>
      coachApi.coverLetterTransform(body, mode),
  });
}

export function useInterviewPrep() {
  return useMutation({
    mutationFn: ({ jdText }: { jdText: string }) => coachApi.interviewPrep(jdText),
  });
}
