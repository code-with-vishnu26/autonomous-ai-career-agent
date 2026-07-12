/**
 * Client-side browser push (Phase 58, ADR-0077). There is no server-side
 * "send a browser notification" action -- `agents/notifications/
 * dispatcher.py`'s own docstring names this exact file as where that
 * channel actually lives: it polls `/notifications/unread` (via
 * `useUnreadNotifications`'s existing 30s interval, no second poll) and
 * calls the real browser `Notification` API for any id it hasn't shown
 * yet. Renders a small permission-request banner only while the user
 * hasn't yet decided ("default"); renders nothing once granted or denied,
 * and nothing at all in a browser/context without `Notification` support
 * (graceful degradation -- e.g. `jsdom` in tests, some mobile browsers).
 */

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { useUnreadNotifications } from "@/hooks/useNotifications";

function browserNotificationsSupported(): boolean {
  return typeof Notification !== "undefined";
}

export function BrowserNotifier() {
  const { data: unread = [] } = useUnreadNotifications();
  const shown = useRef<Set<string>>(new Set());
  const [permission, setPermission] = useState<NotificationPermission | "unsupported">(
    browserNotificationsSupported() ? Notification.permission : "unsupported",
  );

  useEffect(() => {
    if (permission !== "granted") return;
    for (const notification of unread) {
      if (shown.current.has(notification.id)) continue;
      shown.current.add(notification.id);
      void new Notification(notification.title, { body: notification.message });
    }
  }, [unread, permission]);

  if (permission !== "default") return null;

  return (
    <div className="flex items-center justify-between gap-2 border-b border-border bg-muted/50 px-4 py-2 text-sm">
      <span>Enable browser notifications to be alerted about new activity.</span>
      <Button
        variant="outline"
        size="sm"
        onClick={async () => {
          const result = await Notification.requestPermission();
          setPermission(result);
        }}
      >
        Enable
      </Button>
    </div>
  );
}
