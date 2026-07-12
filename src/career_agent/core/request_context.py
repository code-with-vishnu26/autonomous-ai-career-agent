"""Per-request correlation ID (Phase 61, ADR-0079).

A request that fails is only debuggable if every log line it produced can
be tied back together -- across the request-logging middleware, any router
code, and an unhandled-exception log. This module is the single source of
truth for that ID: one ``contextvars.ContextVar``, set once per request by
``api.middleware.request_id_middleware``, read here by every logger in the
process via ``RequestIdLogFilter`` and by ``api/app.py``'s global exception
handler. Never generate a second ID anywhere else.

Framework-agnostic on purpose (no FastAPI import) -- the layering contract
(``tests/test_architecture.py``) keeps ``core`` free of any `api`-layer
dependency; the FastAPI-specific middleware that calls ``set_request_id``
lives in ``api/middleware.py`` instead.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logging import LogRecord

#: Empty string, not ``None`` -- so the logging filter below never has to
#: null-check before assigning it onto a ``LogRecord``.
_request_id: ContextVar[str] = ContextVar("request_id", default="")

#: The header a reverse proxy or an upstream caller may already have set
#: (e.g. an edge proxy's own ``$request_id``) -- reused rather than
#: discarded, so a request keeps the same ID end-to-end when one exists.
REQUEST_ID_HEADER = "X-Request-ID"


def current_request_id() -> str:
    """The active request's correlation ID, or "" outside a request."""
    return _request_id.get()


def set_request_id(request_id: str) -> object:
    """Bind ``request_id`` for the current context; returns a reset token."""
    return _request_id.set(request_id)


def reset_request_id(token: object) -> None:
    """Undo a prior ``set_request_id`` call, restoring the previous value."""
    _request_id.reset(token)  # type: ignore[arg-type]


class RequestIdLogFilter:
    """``logging.Filter``-shaped: stamps every log record with the current request ID.

    Applied once, at the root logger, in ``configure_logging`` -- every
    logger in the process inherits it, not just ``api.*`` loggers, since a
    background job (scheduler, notification dispatch) triggered by a
    request should still be traceable back to it via the same ID.
    """

    def filter(self, record: LogRecord) -> bool:
        """Stamp ``record.request_id`` and always allow the record through."""
        record.request_id = current_request_id()  # type: ignore[attr-defined]
        return True
