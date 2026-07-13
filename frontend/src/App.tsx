import { Route, Routes } from "react-router-dom";
import { AppLayout } from "@/layouts/AppLayout";
import { AuthProvider } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeProvider";
import { useAuth } from "@/hooks/useAuth";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { SessionExpiredScreen } from "@/components/SessionExpiredScreen";
import { LoginPage } from "@/pages/auth/LoginPage";
import { RegisterPage } from "@/pages/auth/RegisterPage";
import { ForgotPasswordPage } from "@/pages/auth/ForgotPasswordPage";
import { ResetPasswordPage } from "@/pages/auth/ResetPasswordPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { SearchJobsPage } from "@/pages/SearchJobsPage";
import { ApplicationsPage } from "@/pages/ApplicationsPage";
import { ReviewQueuePage } from "@/pages/ReviewQueuePage";
import { SubmissionQueuePage } from "@/pages/SubmissionQueuePage";
import { HistoryPage } from "@/pages/HistoryPage";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { OnboardingWizardPage } from "@/pages/OnboardingWizardPage";
import { ProfilePage } from "@/pages/ProfilePage";
import { AccountPage } from "@/pages/AccountPage";
import { NotificationsPage } from "@/pages/NotificationsPage";
import { NotificationSettingsPage } from "@/pages/NotificationSettingsPage";
import { OrganizationsPage } from "@/pages/OrganizationsPage";
import { TeamPage } from "@/pages/TeamPage";
import { BillingPage } from "@/pages/BillingPage";
import { AuditLogPage } from "@/pages/AuditLogPage";
import { AcceptInvitePage } from "@/pages/AcceptInvitePage";
import { AdminPage } from "@/pages/AdminPage";
import { CareerCoachPage } from "@/pages/coach/CareerCoachPage";
import { ResumeAnalysisPage } from "@/pages/coach/ResumeAnalysisPage";
import { JobMatchPage } from "@/pages/coach/JobMatchPage";
import { ResumeSuggestionsPage } from "@/pages/coach/ResumeSuggestionsPage";
import { CoverLetterAssistantPage } from "@/pages/coach/CoverLetterAssistantPage";
import { InterviewPrepPage } from "@/pages/coach/InterviewPrepPage";
import { SkillGapPage } from "@/pages/coach/SkillGapPage";
import { CompanyResearchPage } from "@/pages/coach/CompanyResearchPage";
import { SalaryInsightsPage } from "@/pages/coach/SalaryInsightsPage";
import { WeeklyReportPage } from "@/pages/coach/WeeklyReportPage";
import { CareerRoadmapPage } from "@/pages/coach/CareerRoadmapPage";

function AppRoutes() {
  const { sessionExpired } = useAuth();

  if (sessionExpired) {
    return <SessionExpiredScreen />;
  }

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/search" element={<SearchJobsPage />} />
          <Route path="/applications" element={<ApplicationsPage />} />
          <Route path="/review" element={<ReviewQueuePage />} />
          <Route path="/submission" element={<SubmissionQueuePage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/notification-settings" element={<NotificationSettingsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/onboarding" element={<OnboardingWizardPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="/coach" element={<CareerCoachPage />} />
          <Route path="/coach/resume-analysis" element={<ResumeAnalysisPage />} />
          <Route path="/coach/job-match" element={<JobMatchPage />} />
          <Route path="/coach/resume-suggestions" element={<ResumeSuggestionsPage />} />
          <Route path="/coach/cover-letter" element={<CoverLetterAssistantPage />} />
          <Route path="/coach/interview-prep" element={<InterviewPrepPage />} />
          <Route path="/coach/skill-gap" element={<SkillGapPage />} />
          <Route path="/coach/company-research" element={<CompanyResearchPage />} />
          <Route path="/coach/salary-insights" element={<SalaryInsightsPage />} />
          <Route path="/coach/weekly-report" element={<WeeklyReportPage />} />
          <Route path="/coach/roadmap" element={<CareerRoadmapPage />} />
          <Route path="/organizations" element={<OrganizationsPage />} />
          <Route path="/organizations/:organizationId/team" element={<TeamPage />} />
          <Route
            path="/organizations/:organizationId/billing"
            element={<BillingPage />}
          />
          <Route path="/organizations/:organizationId/audit" element={<AuditLogPage />} />
          <Route path="/accept-invite" element={<AcceptInvitePage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Route>
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </ThemeProvider>
  );
}
