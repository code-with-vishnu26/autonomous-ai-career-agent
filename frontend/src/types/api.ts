/**
 * Mirrors the Pydantic response models the FastAPI dashboard API (Phase 54,
 * ADR-0072) actually serializes -- field-for-field, not a redesign. Keep
 * this file in lockstep with `src/career_agent/domain/*.py` and
 * `src/career_agent/api/routers/*.py`; it is the only place shapes are
 * declared, mirroring the backend's "one store, one router" discipline.
 */

export type ApplicationSessionStatus =
  | "READY_FOR_REVIEW"
  | "BLOCKED"
  | "LOGIN_REQUIRED_TIMEOUT"
  | "UNSUPPORTED_PROVIDER";

export interface ApplicationSession {
  id: string;
  provider: string;
  company: string;
  job_title: string;
  url: string;
  opportunity_id: string;
  status: ApplicationSessionStatus;
  resume_variant_id: string | null;
  cover_letter_body: string | null;
  filled_fields: string[];
  detected_fields: string[];
  uploaded_files: string[];
  missing_fields: string[];
  warnings: string[];
  created_at: string;
}

export type ApprovalStatus = "WAITING" | "APPROVED" | "REJECTED" | "CANCELLED" | "TIMEOUT";

export interface ReviewSession {
  id: string;
  application_session_id: string;
  company: string;
  job_title: string;
  provider: string;
  approval_status: ApprovalStatus;
  review_notes: string | null;
  created_at: string;
  approved_at: string | null;
}

export type SubmissionStatus =
  | "SUBMITTED"
  | "FAILED"
  | "UNKNOWN"
  | "ABORTED"
  | "CANCELLED"
  | "REFUSED";

export interface SubmissionResult {
  id: string;
  application_session_id: string;
  review_session_id: string;
  opportunity_id: string;
  provider: string;
  company: string;
  job_title: string;
  submitted: boolean;
  status: SubmissionStatus;
  confirmation_id: string | null;
  confirmation_url: string | null;
  submitted_at: string | null;
  duration_seconds: number | null;
  warnings: string[];
  refusal_reason: string | null;
}

export interface TailoredWorkEntry {
  source_entry_id: string;
  position: string;
  highlights: string[];
}

export interface TailoredProjectEntry {
  source_entry_id: string;
  name: string;
  highlights: string[];
}

export interface TailoredContent {
  summary: string;
  work: TailoredWorkEntry[];
  skills: string[];
  projects: TailoredProjectEntry[];
}

export interface ResumeVariant {
  id: string;
  category: string;
  profile_version: string;
  content: TailoredContent;
  created_at: string;
}

export interface AnalyticsSummary {
  applications_by_status: Record<string, number>;
  reviews_by_status: Record<string, number>;
  submissions_by_status: Record<string, number>;
}

export interface RedactedSettings {
  values: Record<string, unknown>;
  configured_secrets: Record<string, boolean>;
}

export interface HealthStatus {
  status: string;
  version: string;
}
