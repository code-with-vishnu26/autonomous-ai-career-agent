import type { LucideIcon } from "lucide-react";
import {
  LayoutDashboard,
  Search,
  FileText,
  ClipboardCheck,
  Send,
  History,
  BarChart3,
  Settings as SettingsIcon,
  UserCircle,
  ShieldCheck,
  Sparkles,
  Target,
  Wand2,
  Mail,
  Building2,
  MessagesSquare,
  TrendingUp,
  DollarSign,
  CalendarClock,
  Map,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/search", label: "Search Jobs", icon: Search },
  { to: "/applications", label: "Applications", icon: FileText },
  { to: "/review", label: "Review Queue", icon: ClipboardCheck },
  { to: "/submission", label: "Submission Queue", icon: Send },
  { to: "/history", label: "History", icon: History },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

/**
 * Phase 57 (ADR-0075). Six of these (Resume Analysis, Job Match, Resume
 * Suggestions, Cover Letter, Interview Prep, Skill Gap) are real, wired to
 * `/coach/*`. Four (Company Research, Salary Insights, Weekly Report,
 * Career Roadmap) have no real data source in this codebase and route to
 * a page that honestly says so -- see `DeferredCoachFeature.tsx`.
 */
export const COACH_NAV_ITEMS: NavItem[] = [
  { to: "/coach", label: "Career Coach", icon: Sparkles },
  { to: "/coach/resume-analysis", label: "Resume Analysis", icon: FileText },
  { to: "/coach/job-match", label: "Job Match Score", icon: Target },
  { to: "/coach/resume-suggestions", label: "Resume Suggestions", icon: Wand2 },
  { to: "/coach/cover-letter", label: "Cover Letter Assistant", icon: Mail },
  { to: "/coach/interview-prep", label: "Interview Prep", icon: MessagesSquare },
  { to: "/coach/skill-gap", label: "Skill Gap", icon: TrendingUp },
  { to: "/coach/company-research", label: "Company Research", icon: Building2 },
  { to: "/coach/salary-insights", label: "Salary Insights", icon: DollarSign },
  { to: "/coach/weekly-report", label: "Weekly Career Report", icon: CalendarClock },
  { to: "/coach/roadmap", label: "Career Roadmap", icon: Map },
];

export const ACCOUNT_NAV_ITEMS: NavItem[] = [
  { to: "/profile", label: "Profile", icon: UserCircle },
  { to: "/account", label: "Account", icon: ShieldCheck },
];
