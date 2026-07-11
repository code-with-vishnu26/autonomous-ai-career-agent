import { describe, expect, it } from "vitest";
import {
  applicationsPerDay,
  countBy,
  joinReviewsWithSessions,
  readyForSubmission,
} from "./derive";
import type { ApplicationSession, ReviewSession, SubmissionResult } from "@/types/api";

function session(overrides: Partial<ApplicationSession> = {}): ApplicationSession {
  return {
    id: "sess-1",
    provider: "greenhouse",
    company: "Acme",
    job_title: "Engineer",
    url: "https://example.invalid/job",
    opportunity_id: "opp-1",
    status: "READY_FOR_REVIEW",
    resume_variant_id: null,
    cover_letter_body: null,
    filled_fields: [],
    detected_fields: [],
    uploaded_files: [],
    missing_fields: [],
    warnings: [],
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function review(overrides: Partial<ReviewSession> = {}): ReviewSession {
  return {
    id: "review-1",
    application_session_id: "sess-1",
    company: "Acme",
    job_title: "Engineer",
    provider: "greenhouse",
    approval_status: "WAITING",
    review_notes: null,
    created_at: "2026-01-01T00:00:00Z",
    approved_at: null,
    ...overrides,
  };
}

function submissionResult(overrides: Partial<SubmissionResult> = {}): SubmissionResult {
  return {
    id: "sub-1",
    application_session_id: "sess-1",
    review_session_id: "review-1",
    opportunity_id: "opp-1",
    provider: "greenhouse",
    company: "Acme",
    job_title: "Engineer",
    submitted: true,
    status: "SUBMITTED",
    confirmation_id: null,
    confirmation_url: null,
    submitted_at: "2026-01-02T00:00:00Z",
    duration_seconds: null,
    warnings: [],
    refusal_reason: null,
    ...overrides,
  };
}

describe("joinReviewsWithSessions", () => {
  it("pairs each review with its matching session", () => {
    const result = joinReviewsWithSessions([review()], [session()]);
    expect(result).toHaveLength(1);
    expect(result[0].session?.id).toBe("sess-1");
  });

  it("leaves session undefined when no match exists", () => {
    const result = joinReviewsWithSessions(
      [review({ application_session_id: "missing" })],
      [session()],
    );
    expect(result[0].session).toBeUndefined();
  });
});

describe("readyForSubmission", () => {
  it("includes an approved review with no submission attempt", () => {
    const result = readyForSubmission([review({ approval_status: "APPROVED" })], []);
    expect(result).toHaveLength(1);
  });

  it("excludes a review that already has a submission attempt", () => {
    const result = readyForSubmission(
      [review({ approval_status: "APPROVED" })],
      [submissionResult()],
    );
    expect(result).toHaveLength(0);
  });

  it("excludes a review that was never approved", () => {
    const result = readyForSubmission([review({ approval_status: "WAITING" })], []);
    expect(result).toHaveLength(0);
  });
});

describe("countBy", () => {
  it("counts items by the given key", () => {
    const result = countBy(["a", "b", "a", "c", "a"], (x) => x);
    expect(result).toEqual({ a: 3, b: 1, c: 1 });
  });

  it("returns an empty object for an empty list", () => {
    expect(countBy([], (x: string) => x)).toEqual({});
  });
});

describe("applicationsPerDay", () => {
  it("groups sessions by their created_at date", () => {
    const result = applicationsPerDay([
      session({ created_at: "2026-01-01T09:00:00Z" }),
      session({ created_at: "2026-01-01T15:00:00Z" }),
      session({ created_at: "2026-01-02T09:00:00Z" }),
    ]);
    expect(result).toEqual([
      { date: "2026-01-01", count: 2 },
      { date: "2026-01-02", count: 1 },
    ]);
  });

  it("returns an empty array for no sessions", () => {
    expect(applicationsPerDay([])).toEqual([]);
  });
});
