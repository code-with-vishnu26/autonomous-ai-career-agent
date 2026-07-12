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

export type UserRole = "user" | "admin";

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  role: UserRole;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

/**
 * Mirrors `domain/job_preferences.py::JobPreferences` field-for-field.
 * Only `preferred_titles`/`alternative_titles`/`work_mode`/`countries`/
 * `keywords_exclude` are actually consumed by discovery today -- the rest
 * are captured configuration surface, not yet enforced (see the backend
 * docstring for the exact list).
 */
export interface JobPreferences {
  preferred_titles: string[];
  alternative_titles: string[];
  seniority: string | null;
  experience_years_min: number | null;
  experience_years_max: number | null;
  employment_types: string[];
  work_mode: string[];
  countries: string[];
  states: string[];
  cities: string[];
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  preferred_companies: string[];
  blacklisted_companies: string[];
  industries: string[];
  visa_sponsorship_required: boolean | null;
  work_authorization: string | null;
  preferred_technologies: string[];
  keywords_include: string[];
  keywords_exclude: string[];
  max_applications_per_day: number | null;
  require_human_confirmation: boolean;
  auto_tailor_resume: boolean;
  auto_generate_cover_letter: boolean;
  preferred_ats_providers: string[];
  time_zone: string | null;
}

/**
 * Career Coach types (Phase 57, ADR-0075). Mirror
 * `career_agent/agents/coach/*.py`'s Pydantic response models field-for-field.
 */
export interface MatchedSkill {
  keyword: string;
  kind: "hard" | "soft";
}

export interface MissingKeyword {
  keyword: string;
  kind: "hard" | "soft";
}

export interface BulletIssue {
  text: string;
  reason: string;
}

export interface FormattingIssue {
  reason: string;
}

export interface ResumeAnalysis {
  ats_score: number;
  matched_keywords: MatchedSkill[];
  missing_keywords: MissingKeyword[];
  weak_bullets: BulletIssue[];
  formatting_issues: FormattingIssue[];
}

export interface JobMatchResult {
  match_score: number;
  matched_keywords: MatchedSkill[];
  missing_keywords: MissingKeyword[];
}

export interface PrioritizedGap {
  keyword: string;
  kind: string;
  reason: string;
}

export interface SkillGapReport {
  qualifies_percent: number;
  missing_skills: PrioritizedGap[];
}

export interface ResumeSuggestion {
  original: string;
  suggested: string;
  reason: string;
  confidence: number;
}

export type CoverLetterMode = "rewrite" | "shorten" | "more_formal" | "more_technical";

export interface CoverLetterTransformResult {
  mode: string;
  original: string;
  transformed: string;
  confidence: number;
}

export interface PrepQuestion {
  question: string;
  why: string;
}

export interface InterviewPrepResult {
  technical_questions: PrepQuestion[];
  behavioral_questions: PrepQuestion[];
  role_specific_questions: PrepQuestion[];
  star_guidance: string;
}
