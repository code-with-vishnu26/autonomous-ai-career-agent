import { NavLink } from "react-router-dom";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { COACH_NAV_ITEMS } from "@/layouts/nav-items";

const FEATURES = COACH_NAV_ITEMS.filter((item) => item.to !== "/coach");

export function CareerCoachPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Career Coach</h1>
      <Callout>
        Advisory only: nothing here is ever applied automatically. Every
        suggestion explains why it was made, and every AI-drafted claim is
        verified against your own resume text before it is ever shown to you
        -- see each feature's page for details.
      </Callout>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to}>
            <Card className="h-full transition-colors hover:bg-accent">
              <CardHeader className="flex flex-row items-center gap-3">
                <Icon className="h-5 w-5 text-primary" />
                <CardTitle className="text-base">{label}</CardTitle>
              </CardHeader>
            </Card>
          </NavLink>
        ))}
      </div>
    </div>
  );
}
