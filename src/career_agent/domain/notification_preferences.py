"""Per-user notification preferences (Phase 58, ADR-0077).

Follows `domain/job_preferences.py`'s own precedent (ADR-0064): a wholly
separate model, never merged into `User`/`MasterProfile` -- preferences
are delivery/behavior configuration, not an applicant-facing fact the
truthfulness gate would ever ground against.
"""

from __future__ import annotations

from datetime import time
from typing import Literal

from pydantic import BaseModel, Field

from .notification import NotificationCategory

WeeklyDigestDay = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class NotificationPreferences(BaseModel):
    """One user's notification delivery preferences.

    Defaults are all-on, in-app-only -- the one channel that needs no
    external configuration (no SMTP host, no webhook URL) to actually work.
    """

    enable_email: bool = False
    enable_browser: bool = True
    enable_in_app: bool = True
    enable_reminders: bool = True
    enable_digests: bool = True
    #: Quiet hours suppress email/browser/webhook delivery (never in-app
    #: storage -- a notification is still recorded, just not pushed) --
    #: both in the user's own `timezone`. `None` means no quiet hours.
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    timezone: str = "UTC"
    daily_digest_time: time = time(hour=8, minute=0)
    weekly_digest_day: WeeklyDigestDay = "mon"
    #: Which notification categories the user wants at all -- an empty
    #: list is NOT "opt out of everything silently"; it is "not yet
    #: customized," meaning every category shown in `notification.py`
    #: applies. A caller that wants to know if a specific category is
    #: enabled must check membership only when this list is non-empty.
    categories: list[NotificationCategory] = Field(default_factory=list)

    def wants_category(self, category: NotificationCategory) -> bool:
        """Whether ``category`` should be delivered, per this preference set."""
        return not self.categories or category in self.categories
