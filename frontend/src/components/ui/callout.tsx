import type { HTMLAttributes } from "react";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";

/** A muted, informational banner -- used to name a CLI-only capability honestly
 * rather than fabricate a working button for an endpoint that doesn't exist
 * (Phase 54, ADR-0072, is read-only). */
export function Callout({ className, children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-md border border-border bg-muted/50 p-3 text-sm text-muted-foreground",
        className,
      )}
      {...props}
    >
      <Info className="mt-0.5 h-4 w-4 shrink-0" />
      <div>{children}</div>
    </div>
  );
}
