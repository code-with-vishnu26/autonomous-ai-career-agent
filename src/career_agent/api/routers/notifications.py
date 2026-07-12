"""Notification Center endpoints (Phase 58, ADR-0077).

Every route here is scoped to ``get_current_user``'s own notifications --
``SqliteNotificationStore``'s own ``user_id``-scoped methods are what
enforce that (never a cross-user leak by construction, the same
"user_id lives in the SQL row" discipline Phase 56 established for every
other per-user table).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from career_agent.api.dependencies import get_notification_store
from career_agent.api.security import get_current_user
from career_agent.domain.notification import Notification
from career_agent.domain.user import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


class MarkReadRequest(BaseModel):
    """Body for ``POST /notifications/read``."""

    notification_id: str


class MarkAllReadResponse(BaseModel):
    """Response for ``POST /notifications/read-all``."""

    marked: int


@router.get("", response_model=list[Notification])
def list_notifications(
    current_user: User = Depends(get_current_user),
    notification_store=Depends(get_notification_store),
) -> list[Notification]:
    """Every notification owned by the caller, newest first."""
    return notification_store.by_user(current_user.id)


@router.get("/unread", response_model=list[Notification])
def list_unread_notifications(
    current_user: User = Depends(get_current_user),
    notification_store=Depends(get_notification_store),
) -> list[Notification]:
    """The caller's unread notifications, newest first."""
    return notification_store.unread_by_user(current_user.id)


@router.post("/read", response_model=Notification)
def mark_read(
    body: MarkReadRequest,
    current_user: User = Depends(get_current_user),
    notification_store=Depends(get_notification_store),
) -> Notification:
    """Mark one of the caller's own notifications read."""
    updated = notification_store.mark_read(
        body.notification_id, user_id=current_user.id, read_at=datetime.now(UTC)
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found."
        )
    notification = notification_store.get(body.notification_id, user_id=current_user.id)
    assert notification is not None  # just marked read above
    return notification


@router.post("/read-all", response_model=MarkAllReadResponse)
def mark_all_read(
    current_user: User = Depends(get_current_user),
    notification_store=Depends(get_notification_store),
) -> MarkAllReadResponse:
    """Mark every one of the caller's unread notifications read."""
    marked = notification_store.mark_all_read(
        user_id=current_user.id, read_at=datetime.now(UTC)
    )
    return MarkAllReadResponse(marked=marked)


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    notification_store=Depends(get_notification_store),
) -> None:
    """Delete one of the caller's own notifications."""
    deleted = notification_store.delete(notification_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found."
        )
