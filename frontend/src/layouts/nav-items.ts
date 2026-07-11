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
