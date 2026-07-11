import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

/** Shared loading/error/empty presentation so every page handles an
 * offline `career-agent serve` (or empty store) the same, honest way
 * instead of a blank screen. */
export function QueryState({
  isLoading,
  isError,
  isEmpty,
  emptyMessage,
  children,
}: {
  isLoading: boolean;
  isError: boolean;
  isEmpty?: boolean;
  emptyMessage?: string;
  children: ReactNode;
}) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }
  if (isError) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        Could not reach the dashboard API. Is <code>career-agent serve</code> running?
      </div>
    );
  }
  if (isEmpty) {
    return (
      <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
        {emptyMessage ?? "Nothing here yet."}
      </p>
    );
  }
  return <>{children}</>;
}
