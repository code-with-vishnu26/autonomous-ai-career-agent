"""Notifications & Background Processing (Phase 58, ADR-0077).

Generates, formats, and delivers notifications for the dashboard's own
real events -- resume prepared, review approved/rejected, submission
completed/cancelled/failed, password changed -- plus reminders (pending
review, pending submission, missing promptfoo validation) and digests
(daily/weekly/monthly) computed from the same stores the dashboard
already reads. See ADR-0077 for the event types this phase's audit found
have no real trigger point in the current dashboard/API architecture and
were explicitly deferred rather than faked.
"""

from __future__ import annotations
