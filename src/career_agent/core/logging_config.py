"""Structured logging setup for the Web Dashboard API (Phase 59, ADR-0076).

No new dependency: a small stdlib ``logging.Formatter`` subclass that emits
one JSON object per line (the de facto "structured logging" contract every
container log collector -- Docker, Kubernetes, CloudWatch -- already knows
how to parse) rather than pulling in ``structlog``/``python-json-logger``
for what one small formatter class already does. Plain text remains the
default outside production so a local `career-agent serve` run still reads
naturally in a terminal.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from career_agent.core.request_context import RequestIdLogFilter

if TYPE_CHECKING:
    from career_agent.core.config import Settings

_RESERVED_LOG_RECORD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
)


class JsonFormatter(logging.Formatter):
    """Renders one ``logging.LogRecord`` as one JSON object per line.

    Any ``extra={...}`` fields a caller passed through the standard
    ``logging`` API are included verbatim (e.g. request middleware's
    ``method``/``path``/``status_code``/``duration_ms``) -- this formatter
    never invents fields, it only serializes what was actually logged.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Serialize ``record`` as one JSON line, including any ``extra`` fields."""
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_ATTRS:
                payload[key] = value
        return json.dumps(payload, default=str)


def effective_json_logs(settings: Settings) -> bool:
    """Whether JSON logging should be on: explicit setting, else production-default."""
    if settings.json_logs is not None:
        return settings.json_logs
    return settings.environment == "production"


def configure_logging(settings: Settings) -> None:
    """Configure the root logger once, at process startup.

    Idempotent-in-effect (safe to call more than once -- replaces the
    root handler rather than accumulating a second one), so
    ``career-agent serve`` and any test importing this module directly
    never end up with duplicated log lines.
    """
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    if effective_json_logs(settings):
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s"
            )
        )
    handler.addFilter(RequestIdLogFilter())
    root.addHandler(handler)
