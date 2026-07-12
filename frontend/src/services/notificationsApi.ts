/**
 * Thin fetch wrapper over `/notifications/*` and `/notification-settings`
 * (Phase 58, ADR-0077). Unlike `api.ts` (deliberately GET-only, ADR-0072),
 * this file's endpoints are the caller's own notifications and their own
 * delivery preferences -- the same write-capable-but-still-user-scoped
 * shape `authApi.ts`/`coachApi.ts` already established.
 */

import { apiFetch, apiFetchJson } from "./http";
import type {
  Notification,
  NotificationSettings,
  NotificationSettingsUpdate,
} from "@/types/api";

export const notificationsApi = {
  list: () => apiFetchJson<Notification[]>("/notifications"),
  unread: () => apiFetchJson<Notification[]>("/notifications/unread"),
  markRead: (notificationId: string) =>
    apiFetchJson<Notification>("/notifications/read", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notification_id: notificationId }),
    }),
  markAllRead: () =>
    apiFetchJson<{ marked: number }>("/notifications/read-all", { method: "POST" }),
  remove: async (notificationId: string) => {
    const response = await apiFetch(`/notifications/${notificationId}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error(`Failed to delete notification (${response.status})`);
  },
  getSettings: () => apiFetchJson<NotificationSettings>("/notification-settings"),
  updateSettings: (update: NotificationSettingsUpdate) =>
    apiFetchJson<NotificationSettings>("/notification-settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    }),
};
