import { Callout } from "@/components/ui/callout";

/** Honestly names a Phase 57 feature that has no real data source yet, rather
 * than fabricating one (ADR-0075) -- the same discipline `CliOnlyAction`
 * established in Phase 55 for capabilities this dashboard cannot really do. */
export function DeferredCoachFeature({
  title,
  reason,
}: {
  title: string;
  reason: string;
}) {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <Callout>{reason}</Callout>
    </div>
  );
}
