"""Notification preferences + webhook destination endpoints (Phase 58, ADR-0077).

Deliberately one router surface (``/notification-settings``) over two
stores (``SqliteNotificationPreferencesStore``,
``SqliteWebhookSubscriptionStore``) -- the frontend's Notification
Settings page edits both together, but they stay separate stores because
a webhook URL can carry an embedded secret (a Slack/Discord incoming-
webhook token) that the plain preference toggles never need to.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from career_agent.api.dependencies import (
    get_notification_preferences_store,
    get_webhook_subscription_store,
)
from career_agent.api.security import get_current_user
from career_agent.domain.notification_preferences import NotificationPreferences
from career_agent.domain.user import User

router = APIRouter(prefix="/notification-settings", tags=["notification-settings"])


class NotificationSettingsOut(NotificationPreferences):
    """``NotificationPreferences`` plus whether a webhook is configured.

    The webhook URL itself is never echoed back in a ``GET`` -- only
    whether one is set -- mirroring how this API never echoes back a
    password hash or JWT secret.
    """

    webhook_configured: bool = False


class NotificationSettingsUpdate(NotificationPreferences):
    """Body for ``PATCH /notification-settings``.

    ``webhook_url`` is optional and separate from the inherited
    preference fields: omitted means "leave unchanged," ``""`` means
    "remove the webhook," any other string means "set/replace it."
    """

    webhook_url: str | None = None


@router.get("", response_model=NotificationSettingsOut)
def get_notification_settings(
    current_user: User = Depends(get_current_user),
    preferences_store=Depends(get_notification_preferences_store),
    webhook_store=Depends(get_webhook_subscription_store),
) -> NotificationSettingsOut:
    """The caller's notification preferences, or all-defaults if never saved."""
    preferences = preferences_store.get_or_default(current_user.id)
    webhook_url = webhook_store.get(current_user.id)
    return NotificationSettingsOut(
        **preferences.model_dump(), webhook_configured=bool(webhook_url)
    )


@router.patch("", response_model=NotificationSettingsOut)
def update_notification_settings(
    body: NotificationSettingsUpdate,
    current_user: User = Depends(get_current_user),
    preferences_store=Depends(get_notification_preferences_store),
    webhook_store=Depends(get_webhook_subscription_store),
) -> NotificationSettingsOut:
    """Replace the caller's preferences wholesale; optionally set/clear the webhook."""
    preferences = NotificationPreferences(
        **body.model_dump(exclude={"webhook_url"})
    )
    preferences_store.save(current_user.id, preferences)
    if body.webhook_url == "":
        webhook_store.delete(current_user.id)
    elif body.webhook_url is not None:
        webhook_store.save(current_user.id, body.webhook_url)
    webhook_url = webhook_store.get(current_user.id)
    return NotificationSettingsOut(
        **preferences.model_dump(), webhook_configured=bool(webhook_url)
    )
