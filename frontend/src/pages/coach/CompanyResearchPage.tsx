import { DeferredCoachFeature } from "@/components/coach/DeferredCoachFeature";

export function CompanyResearchPage() {
  return (
    <DeferredCoachFeature
      title="Company Research"
      reason={
        "Not available yet: this project has no company-research/Glassdoor/culture " +
        "data source, and a standing project policy (ADR-0036) rules out scraping " +
        "one. Fabricating company insights would violate the Career Coach's own " +
        "‘never fabricate’ principle, so this feature is deferred rather " +
        "than faked (ADR-0075) until a real, licensed data source is integrated."
      }
    />
  );
}
