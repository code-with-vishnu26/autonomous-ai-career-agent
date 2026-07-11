"""Workday adapter (Phase 48, ADR-0066) -- explicit stub.

Unlike every other adapter in this package, **no structured API and no
``FormFiller`` exist anywhere in this codebase for Workday** -- ``search()``
has nothing real to delegate to. Workday is a multi-tenant platform with
no public discovery API this project has integrated, and (per
:mod:`career_agent.domain.models.Company`'s own ``ats_kind`` Literal
already anticipating it) its per-tenant deployments vary enough that a
single static integration would be guessing, the same category of risk
that kept :class:`~career_agent.agents.apply.form_fillers.AshbyFormFiller`
an explicit stub rather than a guessed implementation.

``search()`` therefore always raises :class:`FeatureUnavailableError`
naming the real gap -- never a silent empty result, which would be
indistinguishable from "searched and found nothing."
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from career_agent.integrations.adapters.base import (
    AdapterCapabilities,
    BrowserAdapterMixin,
    FeatureUnavailableError,
)

if TYPE_CHECKING:
    from career_agent.domain.models import Opportunity


class WorkdayAdapter(BrowserAdapterMixin):
    """Recognizes Workday URLs; every data-fetching method is an honest stub."""

    provider = "workday"
    capabilities = AdapterCapabilities()

    def supports(self, url: str) -> bool:
        """Workday's real, publicly documented multi-tenant hosting domain."""
        return "myworkdayjobs.com" in url.lower()

    async def search(self, *, since: datetime, **_: object) -> list[Opportunity]:
        """Always raises -- no structured Workday integration exists yet."""
        raise FeatureUnavailableError(
            "workday: no structured discovery API is integrated for this "
            "platform yet -- see ADR-0066. A real Workday integration "
            "needs per-tenant verification before it can be built, the "
            "same discipline that kept AshbyFormFiller a stub."
        )
