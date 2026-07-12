"""Reusable email templates (Phase 58, ADR-0077).

Pure functions, ``(subject, body) -> tuple[str, str]`` -- no I/O, no
formatting decision left implicit for a caller to get wrong. Plain text
only (no HTML/MIME multipart): this project's other integrations
(Telegram, ntfy) are plain-text too, and a plain-text email renders
correctly everywhere without a templating engine dependency.
"""

from __future__ import annotations


def welcome_email(*, display_name: str | None, email: str) -> tuple[str, str]:
    """New-account welcome, sent once at registration."""
    name = display_name or email
    subject = "Welcome to Autonomous AI Career Agent"
    body = (
        f"Hi {name},\n\n"
        "Your account is ready. Log in to your dashboard to review "
        "prepared applications, use the Career Coach, and manage your "
        "notification preferences.\n\n"
        "-- Autonomous AI Career Agent"
    )
    return subject, body


def password_reset_email(*, reset_link: str) -> tuple[str, str]:
    """Password-reset link (Phase 56's `/auth/forgot-password` flow)."""
    subject = "Reset your password"
    body = (
        "A password reset was requested for your account.\n\n"
        f"Reset link: {reset_link}\n\n"
        "If you didn't request this, you can ignore this email -- your "
        "password will not change unless you use the link above."
    )
    return subject, body


def password_changed_email() -> tuple[str, str]:
    """Confirmation sent after a reset actually completes."""
    subject = "Your password was changed"
    body = (
        "Your password was just changed. Every existing session has been "
        "signed out; you'll need to log in again anywhere you were "
        "signed in.\n\n"
        "If you didn't make this change, someone else may have access to "
        "your account -- reset your password again immediately."
    )
    return subject, body


def review_reminder_email(*, count: int) -> tuple[str, str]:
    """Sent when one or more prepared applications are still awaiting review."""
    subject = f"{count} application(s) waiting for your review"
    body = (
        f"You have {count} prepared application(s) sitting in your "
        "Review Queue. Open the dashboard to approve or reject them."
    )
    return subject, body


def submission_confirmation_email(
    *, company: str, job_title: str, status: str
) -> tuple[str, str]:
    """Sent after a real submission attempt completes (any status)."""
    subject = f"Submission {status.lower()}: {job_title} at {company}"
    body = (
        f"Your submission to {company} for {job_title} finished with "
        f"status: {status}.\n\n"
        "See the Submission Queue in your dashboard for full detail."
    )
    return subject, body


def invitation_email(
    *, organization_name: str, role: str, invite_link: str
) -> tuple[str, str]:
    """Sent when someone is invited to join an organization (Phase 60, ADR-0078)."""
    subject = f"You've been invited to join {organization_name}"
    body = (
        f"You've been invited to join {organization_name} as a {role}.\n\n"
        f"Accept the invitation: {invite_link}\n\n"
        "If you weren't expecting this, you can safely ignore this email."
    )
    return subject, body


def digest_email(*, period: str, summary_lines: list[str]) -> tuple[str, str]:
    """Daily/weekly/monthly digest from already-formatted plain-text lines.

    ``summary_lines`` come from
    :mod:`~career_agent.agents.notifications.digest_generator`.
    """
    subject = f"Your {period} summary"
    body = "\n".join(summary_lines) if summary_lines else "Nothing new to report."
    return subject, body
