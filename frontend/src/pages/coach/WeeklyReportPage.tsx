import { DeferredCoachFeature } from "@/components/coach/DeferredCoachFeature";

export function WeeklyReportPage() {
  return (
    <DeferredCoachFeature
      title="Weekly Career Report"
      reason={
        "Not available yet: a real weekly report needs outcome data (interviews, " +
        "rejections, offers), but this project's interview/rejection outcome " +
        "tracking (the old CLI-only `record_outcome`/`outcome_rows` pipeline) " +
        "was never connected to the dashboard's newer application/review/" +
        "submission stores. Deferred rather than faked (ADR-0075) until those " +
        "two pipelines are reconciled."
      }
    />
  );
}
