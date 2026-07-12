/**
 * Pure client-side joins over the existing API responses -- presentation
 * logic only, the same "Counter over an existing field" discipline
 * `api/routers/analytics.py` already applies server-side. No new business
 * rule is introduced: every predicate here reuses a status value the
 * backend already returns (`approval_status === "APPROVED"`,
 * `status === "READY_FOR_REVIEW"`), never a new one.
 */

import type { ApplicationSession, ReviewSession, SubmissionResult } from "@/types/api";

/** Approved reviews whose application session has no recorded submission
 * attempt yet -- the Submission Queue's "Ready" bucket. Never itself
 * triggers a submission; `career-agent submit` is the only entry point
 * that can (ADR-0071). */
export function readyForSubmission(
  reviews: ReviewSession[],
  submissions: SubmissionResult[],
): ReviewSession[] {
  const attempted = new Set(submissions.map((result) => result.application_session_id));
  return reviews.filter(
    (review) => review.approval_status === "APPROVED" && !attempted.has(review.application_session_id),
  );
}

export function countBy<T>(items: T[], key: (item: T) => string): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of items) {
    const k = key(item);
    counts[k] = (counts[k] ?? 0) + 1;
  }
  return counts;
}

export function applicationsPerDay(sessions: ApplicationSession[]): { date: string; count: number }[] {
  const counts = countBy(sessions, (s) => s.created_at.slice(0, 10));
  return Object.entries(counts)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, count]) => ({ date, count }));
}
