import { DeferredCoachFeature } from "@/components/coach/DeferredCoachFeature";

export function SalaryInsightsPage() {
  return (
    <DeferredCoachFeature
      title="Salary Insights"
      reason={
        "Not available yet: this project has no salary-benchmarking data source " +
        "integrated (no Levels.fyi/Glassdoor/BLS API), and generating a number " +
        "without one would be a fabricated figure presented as real market data. " +
        "Deferred rather than faked (ADR-0075) until a real data source is wired in."
      }
    />
  );
}
