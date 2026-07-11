import { Badge } from "@/components/ui/badge";

const VARIANT_BY_STATUS: Record<string, "success" | "warning" | "destructive" | "muted" | "outline"> = {
  READY_FOR_REVIEW: "warning",
  BLOCKED: "destructive",
  LOGIN_REQUIRED_TIMEOUT: "destructive",
  UNSUPPORTED_PROVIDER: "muted",
  WAITING: "warning",
  APPROVED: "success",
  REJECTED: "destructive",
  CANCELLED: "muted",
  TIMEOUT: "muted",
  SUBMITTED: "success",
  FAILED: "destructive",
  UNKNOWN: "muted",
  ABORTED: "destructive",
  REFUSED: "destructive",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge variant={VARIANT_BY_STATUS[status] ?? "outline"}>{status}</Badge>;
}
