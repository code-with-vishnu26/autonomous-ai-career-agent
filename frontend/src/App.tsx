import { Route, Routes } from "react-router-dom";
import { AppLayout } from "@/layouts/AppLayout";
import { DashboardPage } from "@/pages/DashboardPage";
import { SearchJobsPage } from "@/pages/SearchJobsPage";
import { ApplicationsPage } from "@/pages/ApplicationsPage";
import { ReviewQueuePage } from "@/pages/ReviewQueuePage";
import { SubmissionQueuePage } from "@/pages/SubmissionQueuePage";
import { HistoryPage } from "@/pages/HistoryPage";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { SettingsPage } from "@/pages/SettingsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/search" element={<SearchJobsPage />} />
        <Route path="/applications" element={<ApplicationsPage />} />
        <Route path="/review" element={<ReviewQueuePage />} />
        <Route path="/submission" element={<SubmissionQueuePage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
