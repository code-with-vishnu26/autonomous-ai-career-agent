"""Real SMTP email delivery (Phase 58, ADR-0077).

Standard-library ``smtplib``/``email.mime`` only -- no new dependency, the
same "raw HTTP over a dependency SDK" discipline
:mod:`career_agent.integrations.notifications`'s ``TelegramNotifier``/
``NtfyNotifier`` already hold themselves to. Plain text only (see
``agents/notifications/templates.py``'s own reasoning).

**Never fabricates delivery success** (this phase's own brief): a send
either genuinely completes against a real SMTP server, or raises --
callers (``agents/notifications/dispatcher.py``) catch the exception and
record a ``FAILED``/``SKIPPED``
:class:`~career_agent.domain.notification.DeliveryAttempt`, never a
silently-assumed ``SENT``.
"""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from typing import Protocol, runtime_checkable


class EmailSendError(Exception):
    """A real SMTP send attempt failed."""


@runtime_checkable
class EmailSender(Protocol):
    """Send one plain-text email. Must raise on failure, never fabricate success."""

    async def send(self, *, to: str, subject: str, body: str) -> None:
        """Send. Raises on failure -- never returns having faked a send."""
        ...


class SmtpEmailSender:
    """A real :class:`EmailSender` backed by ``smtplib``."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        use_tls: bool,
        from_address: str,
    ) -> None:
        """Configure with real SMTP connection details."""
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._from_address = from_address

    async def send(self, *, to: str, subject: str, body: str) -> None:
        """Send one plain-text email.

        Synchronous under the hood (SMTP has no real async stdlib client)
        -- callers on the async path accept the brief blocking cost of one
        SMTP round trip rather than adding a new async-SMTP dependency for
        a single-user-scale notification volume. Raises
        :class:`EmailSendError` on any failure -- never returns having
        silently not sent anything.
        """
        message = MIMEText(body, "plain", "utf-8")
        message["Subject"] = subject
        message["From"] = self._from_address
        message["To"] = to
        try:
            with smtplib.SMTP(self._host, self._port, timeout=10) as client:
                if self._use_tls:
                    client.starttls()
                if self._username and self._password:
                    client.login(self._username, self._password)
                client.sendmail(self._from_address, [to], message.as_string())
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailSendError(
                f"SMTP send to {self._host}:{self._port} failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
