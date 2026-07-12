import { NavLink } from "react-router-dom";
import { Briefcase } from "lucide-react";
import { cn } from "@/lib/utils";
import { ACCOUNT_NAV_ITEMS, COACH_NAV_ITEMS, NAV_ITEMS } from "./nav-items";

function NavLinks({ items, onNavigate }: { items: typeof NAV_ITEMS; onNavigate?: () => void }) {
  return (
    <>
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )
          }
        >
          <Icon className="h-4 w-4 shrink-0" />
          {label}
        </NavLink>
      ))}
    </>
  );
}

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border p-4">
        <Briefcase className="h-5 w-5 text-primary" />
        <span className="font-semibold">Career Agent</span>
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto p-2">
        <NavLinks items={NAV_ITEMS} onNavigate={onNavigate} />
        <div className="px-3 pb-1 pt-4 text-xs font-semibold uppercase text-muted-foreground">
          Career Coach ⭐
        </div>
        <NavLinks items={COACH_NAV_ITEMS} onNavigate={onNavigate} />
      </nav>
      <nav className="space-y-1 border-t border-border p-2">
        <NavLinks items={ACCOUNT_NAV_ITEMS} onNavigate={onNavigate} />
      </nav>
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="hidden w-60 shrink-0 border-r border-border md:block">
      <SidebarContent />
    </aside>
  );
}
