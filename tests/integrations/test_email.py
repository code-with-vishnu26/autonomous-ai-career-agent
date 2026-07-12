"""Phase 58 (ADR-0077): SmtpEmailSender -- real SMTP, never a fabricated send."""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from career_agent.integrations.email import EmailSendError, SmtpEmailSender


def _sender(**overrides: object) -> SmtpEmailSender:
    fields: dict[object, object] = {
        "host": "smtp.example.com",
        "port": 587,
        "username": "user",
        "password": "pass",
        "use_tls": True,
        "from_address": "noreply@example.com",
    }
    fields.update(overrides)
    return SmtpEmailSender(**fields)


async def test_send_calls_starttls_login_and_sendmail_when_configured() -> None:
    mock_client = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value = mock_client
        await _sender().send(to="a@b.com", subject="Hi", body="Body")

    mock_client.starttls.assert_called_once()
    mock_client.login.assert_called_once_with("user", "pass")
    mock_client.sendmail.assert_called_once()
    args = mock_client.sendmail.call_args[0]
    assert args[0] == "noreply@example.com"
    assert args[1] == ["a@b.com"]
    assert "Hi" in args[2]


async def test_send_skips_login_when_no_credentials() -> None:
    mock_client = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value = mock_client
        await _sender(username=None, password=None).send(
            to="a@b.com", subject="Hi", body="Body"
        )
    mock_client.login.assert_not_called()


async def test_send_skips_starttls_when_use_tls_false() -> None:
    mock_client = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value = mock_client
        await _sender(use_tls=False).send(to="a@b.com", subject="Hi", body="Body")
    mock_client.starttls.assert_not_called()


async def test_send_wraps_smtp_failure_and_never_fabricates_success() -> None:
    with patch("smtplib.SMTP", side_effect=smtplib.SMTPConnectError(421, "down")):
        with pytest.raises(EmailSendError) as excinfo:
            await _sender().send(to="a@b.com", subject="Hi", body="Body")
    assert "smtp.example.com" in str(excinfo.value)


async def test_send_wraps_os_error() -> None:
    with patch("smtplib.SMTP", side_effect=OSError("connection refused")):
        with pytest.raises(EmailSendError):
            await _sender().send(to="a@b.com", subject="Hi", body="Body")
