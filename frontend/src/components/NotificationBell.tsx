import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, Check, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  useDeleteNotification,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useUnreadNotifications,
} from "@/hooks/useNotifications";
import { notificationTypeVariant } from "@/lib/notificationDisplay";
import type { Notification } from "@/types/api";

const DRAWER_PREVIEW_COUNT = 8;

function NotificationRow({ notification }: { notification: Notification }) {
  const markRead = useMarkNotificationRead();
  const remove = useDeleteNotification();

  return (
    <li className="flex items-start gap-2 border-b border-border px-3 py-2 text-sm last:border-0">
      <Badge variant={notificationTypeVariant(notification.type)} className="mt-0.5 shrink-0">
        {notification.type}
      </Badge>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{notification.title}</p>
        <p className="truncate text-xs text-muted-foreground">{notification.message}</p>
      </div>
      <div className="flex shrink-0 gap-1">
        <Button
          variant="ghost"
          size="icon"
          aria-label="Mark as read"
          onClick={() => markRead.mutate(notification.id)}
        >
          <Check className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Delete notification"
          onClick={() => remove.mutate(notification.id)}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </li>
  );
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const { data: unread = [] } = useUnreadNotifications();
  const markAllRead = useMarkAllNotificationsRead();
  const navigate = useNavigate();

  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="icon"
        aria-label={`Notifications (${unread.length} unread)`}
        onClick={() => setOpen((value) => !value)}
      >
        <Bell className="h-5 w-5" />
        {unread.length > 0 && (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-destructive-foreground">
            {unread.length > 99 ? "99+" : unread.length}
          </span>
        )}
      </Button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-50 mt-2 w-80 rounded-md border border-border bg-popover shadow-lg">
            <div className="flex items-center justify-between border-b border-border px-3 py-2">
              <span className="text-sm font-medium">Notifications</span>
              <Button
                variant="ghost"
                size="sm"
                disabled={unread.length === 0 || markAllRead.isPending}
                onClick={() => markAllRead.mutate()}
              >
                Mark all read
              </Button>
            </div>
            {unread.length === 0 ? (
              <p className="p-4 text-center text-sm text-muted-foreground">
                No unread notifications.
              </p>
            ) : (
              <ul className="max-h-96 overflow-y-auto">
                {unread.slice(0, DRAWER_PREVIEW_COUNT).map((notification) => (
                  <NotificationRow key={notification.id} notification={notification} />
                ))}
              </ul>
            )}
            <div className="border-t border-border p-2">
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => {
                  setOpen(false);
                  navigate("/notifications");
                }}
              >
                View all notifications
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
