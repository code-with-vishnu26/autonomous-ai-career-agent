"""Hacker News "Who is Hiring" opportunity source (Phase 4b-feeds-HN).

The first *extraction* source, not a *fetch* source: the input is a thread of
freeform prose comments, and the work is deciding what is a job, what is not,
and how confident we are -- the discovery-side analogue of the truthfulness
gate (ADR-0003). A confident-looking phantom (a reply or a vague post turned
into a clean ``Opportunity``) is fabrication upstream of where we normally catch
it, so this source is deliberately conservative: it emits only when the format
is unambiguously a posting, and everything else is *held* (recorded via a
:class:`HeldCandidateSink`, never silently dropped -- ADR-0013).

Extraction is heuristic (the "Who is Hiring" ``Company | Role | Location | ...``
pipe convention), not LLM-based: LLM extraction is deferred to its own later
phase, to raise recall against this honest-confidence scaffolding rather than
drag nondeterminism into discovery now. Errors therefore fall toward *holding
real jobs* (recoverable) over *emitting phantoms* (corrosive).

Key documented behavior decisions (ADR-0013):
- **Multi-job comment:** parsed per posting-header line; each qualifying line
  emits independently, a bad line among good ones is held on its own -- never
  first-only, never fused.
- **Non-English/mixed-script:** the classifier is script-agnostic and must never
  crash; junk/missing-field checks are structural (punctuation, empty fields,
  word-character presence), not English-keyword allowlists, so a structurally
  valid CJK/RTL post emits.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime

from career_agent.core.interfaces import HeldCandidateSink, HttpClient
from career_agent.domain.identity import domain_of, normalize, opportunity_id
from career_agent.domain.models import HeldCandidate, Opportunity, Provenance
from career_agent.plugins.sources._dates import as_utc

_DEFAULT_BASE_URL = "https://hacker-news.firebaseio.com/v0"
_EMIT_CONFIDENCE = 0.9
_MIN_HEADER_FIELDS = 3  # Company | Role | Location -- conservative on purpose

# Structural junk signals for a role field (script-agnostic -- no English words).
_ROLE_SLOGANS = {
    "we are hiring",
    "we're hiring",
    "hiring",
    "hiring now",
    "join us",
    "join our team",
    "come work with us",
    "multiple roles",
    "various positions",
}
# A candidate advertising themselves, not a job (checked before header parsing,
# because "Who wants to be hired" style posts are also pipe-formatted).
_SEEKING_MARKERS = (
    "seeking work",
    "seeking a position",
    "seeking freelance",
    "seeking:",
    "looking for work",
    "looking for a role",
    "looking for my next",
    "available for hire",
    "open to work",
    "willing to relocate",
    "résumé",
    "resume:",
    "cv:",
    "i'm a ",
    "i am a ",
)
# Weak "this is about hiring but unparseable" signals -> ambiguous_parse rather
# than not_a_posting.
_JOB_ADJACENT = (
    "hiring",
    "we're looking",
    "we are looking",
    "join our",
    "join us",
    "apply",
    "position",
    "roles",
    "growing",
    "reach out",
    "open positions",
    "who is hiring",
)
_URL_OR_EMAIL = re.compile(r"(https?://\S+|[\w.+-]+@[\w-]+\.[\w.-]+)")


class HNSource:
    """Extract job postings from Hacker News "Who is Hiring" threads."""

    def __init__(
        self,
        thread_ids: list[int],
        *,
        client: HttpClient,
        held_sink: HeldCandidateSink,
        confidence_threshold: float = 0.5,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        """Configure the source with thread ids, HTTP client, and a held sink.

        Args:
            thread_ids: HN item ids of "Who is Hiring" threads to read.
            client: HTTP port used to fetch items (injected for fixtures).
            held_sink: where non-emitted candidates are recorded so the discard
                pile stays visible (ADR-0013).
            confidence_threshold: minimum extraction confidence to emit an
                ``Opportunity``; anything below is held.
            base_url: overridable HN Firebase API base.
        """
        self._thread_ids = thread_ids
        self._client = client
        self._sink = held_sink
        self._threshold = confidence_threshold
        self._base_url = base_url.rstrip("/")

    async def fetch(self, since: datetime) -> list[Opportunity]:
        """Return emitted postings; record everything held via the sink."""
        cutoff = as_utc(since)
        opportunities: list[Opportunity] = []
        for thread_id in self._thread_ids:
            thread = await self._client.get_json(
                f"{self._base_url}/item/{thread_id}.json"
            )
            for kid_id in _kids_of(thread):
                comment = await self._client.get_json(
                    f"{self._base_url}/item/{kid_id}.json"
                )
                if not isinstance(comment, dict):
                    continue
                posted_at = _time_of(comment)
                if posted_at is not None and posted_at < cutoff:
                    continue
                for result in self._classify(comment, kid_id, posted_at):
                    if isinstance(result, Opportunity):
                        opportunities.append(result)
                    else:
                        await self._sink.record(result)
        return opportunities

    def _classify(
        self, comment: dict[str, object], kid_id: object, posted_at: datetime | None
    ) -> list[Opportunity | HeldCandidate]:
        """Classify one comment into emitted opportunities and/or held candidates.

        Returns a list because a single comment may contain several postings
        (the multi-job case), each judged independently.
        """
        text = _plain_text(comment.get("text"))
        reference = f"https://news.ycombinator.com/item?id={kid_id}"
        excerpt = text.strip()[:280]

        if _looks_like_seeking_work(text):
            return [self._hold("seeking_work", reference, excerpt, 0.0)]

        headers = _header_lines(text)
        if headers:
            return [
                self._judge_header(line, text, reference, excerpt, posted_at)
                for line in headers
            ]

        if _is_job_adjacent(text):
            return [self._hold("ambiguous_parse", reference, excerpt, 0.15)]
        return [self._hold("not_a_posting", reference, excerpt, 0.0)]

    def _judge_header(
        self,
        line: str,
        full_text: str,
        reference: str,
        excerpt: str,
        posted_at: datetime | None,
    ) -> Opportunity | HeldCandidate:
        """Judge one pipe-delimited header line: emit it or hold below_threshold."""
        fields = [f.strip() for f in line.split("|")]
        # Partial structure is not a confident extraction (holds real 2-field
        # posts too -- the safe failure direction).
        if len(fields) < _MIN_HEADER_FIELDS:
            return self._hold("below_threshold", reference, line.strip()[:280], 0.3)
        company, role = fields[0], fields[1]
        if not company:  # a job with no employer identity is not vouchable
            return self._hold("below_threshold", reference, line.strip()[:280], 0.3)
        if _is_junk_role(role):  # format-recognizable but no real title
            return self._hold("below_threshold", reference, line.strip()[:280], 0.3)

        confidence = _EMIT_CONFIDENCE
        if confidence < self._threshold:  # pragma: no cover - bands are fixed
            return self._hold(
                "below_threshold", reference, line.strip()[:280], confidence
            )

        location = fields[2] or None
        apply_target = _apply_target(fields)
        # Prefer the apply email/URL domain as the canonical employer identity
        # (ADR-0014); fall back to the normalized company text.
        canonical_company = domain_of(apply_target) or normalize(company)
        return Opportunity(
            id=opportunity_id(
                ats_kind=None,
                board_token=None,
                ats_ref=None,  # HN keys on the fingerprint so re-posts dedup
                company=canonical_company,
                title=role,
                location=location,
            ),
            company_id=normalize(company) or company,
            canonical_company=canonical_company,
            title=role,
            source="hn",
            source_url=apply_target or reference,
            provenance=Provenance(
                method="text_extraction",
                reference=reference,
                extraction_confidence=confidence,
            ),
            posted_at=posted_at,
            location=location,
            remote="remote" in line.casefold(),
            description_raw=full_text,
            discovered_at=datetime.now(UTC),
        )

    def _hold(
        self,
        reason: str,
        reference: str,
        excerpt: str,
        confidence: float,
    ) -> HeldCandidate:
        """Build a :class:`HeldCandidate` record for the discard pile."""
        return HeldCandidate(
            source="hn",
            reason=reason,  # type: ignore[arg-type]
            reference=reference,
            raw_excerpt=excerpt,
            extraction_confidence=confidence,
            held_at=datetime.now(UTC),
        )


def _kids_of(thread: object) -> list[object]:
    if isinstance(thread, dict):
        kids = thread.get("kids", [])
        if isinstance(kids, list):
            return kids
    return []


def _time_of(comment: dict[str, object]) -> datetime | None:
    value = comment.get("time")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    return None


def _plain_text(raw: object) -> str:
    """Convert HN's HTML comment body to newline-separated plain text."""
    if not isinstance(raw, str):
        return ""
    text = raw.replace("<p>", "\n").replace("</p>", "\n")
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)


def _header_lines(text: str) -> list[str]:
    """Return lines that look like a pipe-delimited posting header."""
    return [line for line in text.splitlines() if "|" in line and line.strip()]


def _looks_like_seeking_work(text: str) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in _SEEKING_MARKERS)


def _is_job_adjacent(text: str) -> bool:
    lowered = text.casefold()
    return any(keyword in lowered for keyword in _JOB_ADJACENT)


def _is_junk_role(role: str) -> bool:
    """Structural (script-agnostic) check that a role field carries a real title."""
    stripped = role.strip()
    if len(stripped) < 2 or len(stripped) > 80:
        return True
    if "!" in stripped or "?" in stripped:  # real job titles don't
        return True
    if stripped.casefold() in _ROLE_SLOGANS:
        return True
    if not re.search(r"\w", stripped):  # no word characters (unicode-aware)
        return True
    return False


def _apply_target(fields: list[str]) -> str | None:
    """Return the first field that is a URL or email (the apply link), if any."""
    for field in fields:
        match = _URL_OR_EMAIL.search(field)
        if match:
            return match.group(0)
    return None
