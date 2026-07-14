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

/** Phase 66 (ADR-0084): deterministic match of the stored Master Profile to a JD. */
export interface ProfileMatchResult {
  profile_version: string;
  match: JobMatchResult;
  skill_gap: SkillGapReport;
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

/** Phase 58, ADR-0077: `/notifications/*` and `/notification-settings`. */
export type NotificationType = "INFO" | "SUCCESS" | "WARNING" | "ERROR" | "REMINDER" | "SYSTEM";

export type NotificationCategory =
  | "resume_prepared"
  | "review_approved"
  | "review_rejected"
  | "submission_completed"
  | "submission_cancelled"
  | "submission_failed"
  | "password_changed"
  | "reminder_pending_review"
  | "reminder_pending_submission"
  | "reminder_promptfoo_validation"
  | "digest_daily"
  | "digest_weekly"
  | "digest_monthly"
  | "system";

export interface Notification {
  id: string;
  type: NotificationType;
  category: NotificationCategory;
  title: string;
  message: string;
  read_at: string | null;
  created_at: string;
}

export type WeeklyDigestDay = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

export interface NotificationSettings {
  enable_email: boolean;
  enable_browser: boolean;
  enable_in_app: boolean;
  enable_reminders: boolean;
  enable_digests: boolean;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  timezone: string;
  daily_digest_time: string;
  weekly_digest_day: WeeklyDigestDay;
  categories: NotificationCategory[];
  webhook_configured: boolean;
}

export interface NotificationSettingsUpdate extends Partial<Omit<NotificationSettings, "webhook_configured">> {
  webhook_url?: string;
}

/** Phase 60, ADR-0078: organizations, teams, roles, billing, audit. */
export type Role = "owner" | "admin" | "recruiter" | "member" | "viewer";

export interface Organization {
  id: string;
  name: string;
  slug: string;
  role: Role;
}

export interface RolePermissions {
  role: Role;
  permissions: string[];
}

export interface Member {
  user_id: string;
  email: string;
  display_name: string | null;
  role: Role;
}

export type InvitationStatus = "PENDING" | "ACCEPTED" | "REVOKED" | "EXPIRED";

export interface Invitation {
  id: string;
  email: string;
  role: Role;
  status: InvitationStatus;
  created_at: string;
  expires_at: string;
}

export type PlanId = "free" | "pro" | "enterprise";

export interface Plan {
  id: PlanId;
  name: string;
  monthly_price_cents: number;
  max_seats: number;
  features: string[];
}

export type SubscriptionStatus = "ACTIVE" | "CANCELLED" | "PAST_DUE" | "TRIALING";

export interface Subscription {
  organization_id: string;
  plan_id: PlanId;
  status: SubscriptionStatus;
  current_period_end: string;
}

export interface UsageMetric {
  metric: string;
  count: number;
}

export interface CheckoutResult {
  checkout_url: string;
  subscription: Subscription;
}

export interface AuditLogEntry {
  id: string;
  user_id: string;
  action: string;
  result: string;
  ip_address: string | null;
  created_at: string;
}

export interface AdminOrganization {
  id: string;
  name: string;
  slug: string;
  member_count: number;
}

/**
 * Phase 63, ADR-0081: web-triggered Discover, Review, and Submit. Mirrors
 * `domain/discovery_run.py`, `domain/models.py::Opportunity`, and
 * `api/routers/submission_actions.py::PendingSubmissionStatus`
 * field-for-field.
 */
export type DiscoveryRunStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";

export interface DiscoveryRun {
  id: string;
  user_id: string;
  status: DiscoveryRunStatus;
  started_at: string;
  completed_at: string | null;
  new_count: number;
  source_labels: string[];
  errors: string[];
}

export interface Opportunity {
  id: string;
  company_id: string;
  canonical_company: string;
  title: string;
  source: "ats_api" | "yc" | "hn" | "career_page" | "web_search" | "job_board";
  source_url: string;
  ats_ref: string | null;
  posted_at: string | null;
  location: string | null;
  remote: boolean | null;
  description_raw: string;
  discovered_at: string;
}

export type PendingSubmissionState =
  | "PREPARING"
  | "AWAITING_CONFIRMATION"
  | "SUBMITTING"
  | "DONE"
  | "FAILED";

export interface PendingSubmissionStatus {
  token: string;
  status: PendingSubmissionState;
  company: string | null;
  job_title: string | null;
  error: string | null;
  result_id: string | null;
}

/** Phase 67 (ADR-0085): web-triggered Prepare (tailor a résumé for a job). */
export type PreparationState = "PREPARING" | "DONE" | "FAILED";

export interface PendingPreparationStatus {
  token: string;
  status: PreparationState;
  company: string | null;
  job_title: string | null;
  error: string | null;
  application_session_id: string | null;
}

/** Phase 68 (ADR-0086): a job pasted from a site we don't auto-search. */
export interface PastedJobRequest {
  title: string;
  company: string;
  description: string;
  url?: string;
}

/**
 * Phase 64, ADR-0082: `/user/master-profile`. Mirrors
 * `domain/models.py`'s `MasterProfile` and its nested sections
 * field-for-field -- the same JSON-Resume-shaped source of truth
 * `career-agent prepare`/`submit`/`apply`/`auto` build against, now given
 * a real per-user database store alongside the CLI's file-based one.
 */
export interface BasicsSection {
  name: string;
  email: string;
  phone: string | null;
  summary: string | null;
  location: string | null;
}

export interface WorkEntry {
  id: string;
  name: string;
  position: string;
  start_date: string;
  end_date: string | null;
  highlights: string[];
}

export interface EducationEntry {
  id: string;
  institution: string;
  area: string | null;
  study_type: string | null;
  start_date: string | null;
  end_date: string | null;
}

export interface SkillEntry {
  id: string;
  name: string;
  level: string | null;
  keywords: string[];
}

export interface ProjectEntry {
  id: string;
  name: string;
  description: string | null;
  highlights: string[];
  keywords: string[];
}

export interface LegalStatusSection {
  work_authorized_us: boolean | null;
  requires_sponsorship: boolean | null;
}

export interface MasterProfile {
  version: string;
  basics: BasicsSection;
  work: WorkEntry[];
  education: EducationEntry[];
  skills: SkillEntry[];
  projects: ProjectEntry[];
  legal_status: LegalStatusSection;
}

/** Body for `PUT /user/master-profile` -- no `version`, always server-computed. */
export type MasterProfileUpdate = Omit<MasterProfile, "version">;

/**
 * Phase 71, ADR-0089: `/user/master-profile/import` -- résumé upload and
 * review. Mirrors `api/routers/cv_import.py`'s Pydantic response models
 * field-for-field. A proposal is `UNVERIFIED` until explicitly confirmed
 * or rejected; one never mentioned in a confirm request stays that way.
 */
export interface CvImportProposal {
  proposal_id: string;
  field_path: string;
  proposed_value: string;
  evidence_text: string;
  conflict_ids: string[];
}

export interface CvImportUploadResponse {
  token: string;
  source_type: string;
  proposals: CvImportProposal[];
}

export interface CvImportProposalDecision {
  proposal_id: string;
  confirmed: boolean;
}

export interface CvImportProposalOutcome {
  proposal_id: string;
  field_path: string;
  proposed_value: string;
  outcome: string;
  reason: string;
}

export interface CvImportConfirmResponse {
  results: CvImportProposalOutcome[];
  profile_saved: boolean;
  missing_required_fields: string[];
  profile: MasterProfile | null;
}
