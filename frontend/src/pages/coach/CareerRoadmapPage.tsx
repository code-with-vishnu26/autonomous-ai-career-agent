import { DeferredCoachFeature } from "@/components/coach/DeferredCoachFeature";

export function CareerRoadmapPage() {
  return (
    <DeferredCoachFeature
      title="Career Roadmap"
      reason={
        "Not available yet: a real roadmap needs the same outcome data (which " +
        "roles you interviewed for, which skills correlated with an offer) that " +
        "Weekly Career Report needs and this project doesn't yet track end to " +
        "end. Deferred rather than faked (ADR-0075) -- Skill Gap Analysis " +
        "(available now) is the honest subset of this idea this project can " +
        "support today: a heuristic ranking of missing JD skills, not a " +
        "personalized multi-step career plan."
      }
    />
  );
}
