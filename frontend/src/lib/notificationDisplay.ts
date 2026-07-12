/**
 * Shared presentation mapping for `NotificationType` -> `Badge` variant
 * (Phase 58, ADR-0077). One place so the bell drawer and the full
 * Notification Center page render the same colors for the same type.
 */

import type { NotificationType } from "@/types/api";
import type { BadgeProps } from "@/components/ui/badge";

export function notificationTypeVariant(type: NotificationType): BadgeProps["variant"] {
  switch (type) {
    case "SUCCESS":
      return "success";
    case "WARNING":
    case "REMINDER":
      return "warning";
    case "ERROR":
      return "destructive";
    case "SYSTEM":
      return "muted";
    case "INFO":
    default:
      return "outline";
  }
}
