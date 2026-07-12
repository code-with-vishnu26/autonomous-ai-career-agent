import { useMemo, useState } from "react";
import { Trash2, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Card, CardContent } from "@/components/ui/card";
import { QueryState } from "@/components/QueryState";
import {
  useDeleteNotification,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "@/hooks/useNotifications";
import { notificationTypeVariant } from "@/lib/notificationDisplay";
import type { Notification } from "@/types/api";

type ReadFilter = "all" | "unread" | "read";

const PAGE_SIZE = 15;

export function NotificationsPage() {
  const { data, isLoading, isError } = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();
  const remove = useDeleteNotification();

  const [readFilter, setReadFilter] = useState<ReadFilter>("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const notifications = useMemo(() => data ?? [], [data]);
  const unreadCount = notifications.filter((n) => n.read_at === null).length;

  const filtered = useMemo(() => {
    return notifications.filter((notification) => {
      if (readFilter === "unread" && notification.read_at !== null) return false;
      if (readFilter === "read" && notification.read_at === null) return false;
      if (search.trim()) {
        const query = search.trim().toLowerCase();
        const haystack = `${notification.title} ${notification.message}`.toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      return true;
    });
  }, [notifications, readFilter, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageItems = filtered.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE,
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Notifications</h1>
        <Button
          variant="outline"
          disabled={unreadCount === 0 || markAllRead.isPending}
          onClick={() => markAllRead.mutate()}
        >
          Mark all read ({unreadCount})
        </Button>
      </div>

      <div className="flex flex-wrap gap-2">
        <Select
          value={readFilter}
          onChange={(event) => {
            setReadFilter(event.target.value as ReadFilter);
            setPage(1);
          }}
          className="w-auto"
        >
          <option value="all">All</option>
          <option value="unread">Unread</option>
          <option value="read">Read</option>
        </Select>
        <Input
          placeholder="Search notifications..."
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          className="max-w-xs"
        />
      </div>

      <QueryState
        isLoading={isLoading}
        isError={isError}
        isEmpty={filtered.length === 0}
        emptyMessage="No notifications match this filter."
      >
        <div className="space-y-2">
          {pageItems.map((notification) => (
            <NotificationCard
              key={notification.id}
              notification={notification}
              onMarkRead={() => markRead.mutate(notification.id)}
              onDelete={() => remove.mutate(notification.id)}
            />
          ))}
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2 pt-2">
            <Button
              variant="outline"
              size="sm"
              disabled={currentPage <= 1}
              onClick={() => setPage((value) => value - 1)}
            >
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {currentPage} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={currentPage >= totalPages}
              onClick={() => setPage((value) => value + 1)}
            >
              Next
            </Button>
          </div>
        )}
      </QueryState>
    </div>
  );
}

function NotificationCard({
  notification,
  onMarkRead,
  onDelete,
}: {
  notification: Notification;
  onMarkRead: () => void;
  onDelete: () => void;
}) {
  return (
    <Card className={notification.read_at === null ? "border-primary/40" : undefined}>
      <CardContent className="flex items-start gap-3 py-3">
        <Badge variant={notificationTypeVariant(notification.type)} className="mt-0.5 shrink-0">
          {notification.type}
        </Badge>
        <div className="min-w-0 flex-1">
          <p className="font-medium">{notification.title}</p>
          <p className="text-sm text-muted-foreground">{notification.message}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {new Date(notification.created_at).toLocaleString()}
            {notification.read_at === null ? " -- unread" : ""}
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          {notification.read_at === null && (
            <Button variant="ghost" size="icon" aria-label="Mark as read" onClick={onMarkRead}>
              <Check className="h-4 w-4" />
            </Button>
          )}
          <Button variant="ghost" size="icon" aria-label="Delete notification" onClick={onDelete}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
