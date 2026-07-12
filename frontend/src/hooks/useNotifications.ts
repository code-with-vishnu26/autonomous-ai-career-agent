/**
 * TanStack Query wrappers over `notificationsApi` (Phase 58, ADR-0077).
 * The unread list polls every 30s -- the same "no websockets, just
 * `refetchInterval`" shape the rest of this dashboard already commits to
 * (no real-time push transport exists anywhere in this codebase).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notificationsApi } from "@/services/notificationsApi";
import type { NotificationSettingsUpdate } from "@/types/api";

const UNREAD_POLL_INTERVAL_MS = 30_000;

export function useNotifications() {
  return useQuery({ queryKey: ["notifications"], queryFn: notificationsApi.list });
}

export function useUnreadNotifications() {
  return useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: notificationsApi.unread,
    refetchInterval: UNREAD_POLL_INTERVAL_MS,
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string) => notificationsApi.markRead(notificationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useDeleteNotification() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string) => notificationsApi.remove(notificationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useNotificationSettings() {
  return useQuery({
    queryKey: ["notification-settings"],
    queryFn: notificationsApi.getSettings,
  });
}

export function useUpdateNotificationSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (update: NotificationSettingsUpdate) =>
      notificationsApi.updateSettings(update),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notification-settings"] });
    },
  });
}
