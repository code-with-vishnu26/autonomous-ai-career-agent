"""Adversarial matrix tests for the Hacker News source (the load-bearing slice).

The matrix is the reviewer's, not the source's (the source must not grade its own
homework). Each fixture comment (ids 101-112) instantiates one archetype; the
expected verdict column is authoritative. `test_matrix_verdicts` encodes the
whole matrix in one assertion; the named tests below pin the three cases the
reviewer flagged as separating a real mechanism from a delimiter-counter (#8
clean-format/junk-content, #7 multi-job, #9 no-company).
"""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.core.interfaces import HeldCandidateSink, OpportunitySource
from career_agent.plugins.sources.hn import HNSource
from career_agent.storage.memory import InMemoryHeldCandidateSink
from tests._fakes import FakeHttpClient, load_fixture

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_THREAD_ID = 44444444


def _client() -> FakeHttpClient:
    fixture = load_fixture("hn", "whoishiring.json")
    responses: dict[str, object] = {f"/item/{_THREAD_ID}.json": fixture["thread"]}
    for comment_id, comment in fixture["comments"].items():
        responses[f"/item/{comment_id}.json"] = comment
    return FakeHttpClient(responses)


def _source() -> tuple[HNSource, InMemoryHeldCandidateSink]:
    sink = InMemoryHeldCandidateSink()
    return HNSource([_THREAD_ID], client=_client(), held_sink=sink), sink


def _comment_id(reference: str) -> int:
    return int(reference.rsplit("=", 1)[1])


def test_hn_satisfies_the_opportunity_source_protocol() -> None:
    source, _ = _source()
    assert isinstance(source, OpportunitySource)


def test_in_memory_sink_satisfies_the_held_candidate_sink_protocol() -> None:
    assert isinstance(InMemoryHeldCandidateSink(), HeldCandidateSink)


async def test_matrix_verdicts() -> None:
    """The whole adversarial matrix in one assertion: which comment emits, and
    which is held with which reason. This is the reviewer-defined contract."""
    source, sink = _source()
    opportunities = await source.fetch(_EPOCH)

    emits: dict[int, int] = {}
    for opp in opportunities:
        cid = _comment_id(opp.provenance.reference)
        emits[cid] = emits.get(cid, 0) + 1

    held: dict[int, list[str]] = {}
    for candidate in sink.held:
        held.setdefault(_comment_id(candidate.reference), []).append(candidate.reason)

    # #1 clean post emits; #7 multi-job emits all three; #10 CJK emits;
    # #11 re-post emits (deduped later, at the agent).
    assert emits == {101: 1, 107: 3, 110: 1, 111: 1}

    # #2-#6, #8, #9, #12 are held, each with the reviewer's expected reason.
    assert held == {
        102: ["not_a_posting"],  # a reply/question
        103: ["seeking_work"],  # a candidate, not a job (pipe-formatted!)
        104: ["ambiguous_parse"],  # vague prose, no structure
        105: ["below_threshold"],  # partial structure (2 fields)
        106: ["not_a_posting"],  # meta noise
        108: ["below_threshold"],  # clean format, junk role content (#8)
        109: ["below_threshold"],  # no company (#9)
        112: ["ambiguous_parse"],  # employer-dense, zero postings (#12)
    }


async def test_clean_post_emits_with_real_fields() -> None:
    """#1 false-positive guard: the clean post MUST emit -- a mechanism that
    holds everything is as broken as one that holds nothing."""
    source, _ = _source()
    opportunities = await source.fetch(_EPOCH)
    acme = next(
        o for o in opportunities if _comment_id(o.provenance.reference) == 101
    )
    assert acme.source == "hn"
    assert acme.title == "Senior Rust Engineer"
    assert acme.company_id == "acme"
    assert acme.location == "Remote (EU)"
    assert acme.remote is True
    assert acme.source_url == "apply@acme.com"
    assert acme.provenance.method == "text_extraction"
    assert acme.provenance.extraction_confidence >= 0.5


async def test_multi_job_comment_emits_each_role_independently() -> None:
    """#7: three roles in one comment become three opportunities -- not the
    first only, not one fused mangle."""
    source, _ = _source()
    opportunities = await source.fetch(_EPOCH)
    globex = [o for o in opportunities if _comment_id(o.provenance.reference) == 107]
    assert {o.title for o in globex} == {
        "Backend Engineer",
        "Frontend Engineer",
        "Data Scientist",
    }


async def test_clean_format_but_junk_role_is_held_not_emitted() -> None:
    """#8: format is recognizable but the role field carries no real title, so
    confidence-tracks-format must NOT emit it."""
    source, sink = _source()
    opportunities = await source.fetch(_EPOCH)
    assert all(_comment_id(o.provenance.reference) != 108 for o in opportunities)
    held_108 = [h for h in sink.held if _comment_id(h.reference) == 108]
    assert [h.reason for h in held_108] == ["below_threshold"]


async def test_missing_company_is_disqualifying() -> None:
    """#9: a job with no employer identity cannot be a vouched Opportunity."""
    source, sink = _source()
    opportunities = await source.fetch(_EPOCH)
    assert all(_comment_id(o.provenance.reference) != 109 for o in opportunities)
    held_109 = [h for h in sink.held if _comment_id(h.reference) == 109]
    assert [h.reason for h in held_109] == ["below_threshold"]


async def test_non_english_post_emits_and_does_not_crash() -> None:
    """#10: script-agnostic. A structurally valid CJK post emits; the parser
    must never throw on unicode."""
    source, _ = _source()
    opportunities = await source.fetch(_EPOCH)
    cjk = next(
        o for o in opportunities if _comment_id(o.provenance.reference) == 110
    )
    assert cjk.title == "ソフトウェアエンジニア"
    assert cjk.company_id  # non-empty company preserved


async def test_no_low_confidence_opportunity_ever_escapes() -> None:
    """The spine invariant: everything emitted as an Opportunity is at or above
    threshold; everything held is below it. No confident phantom escapes."""
    source, sink = _source()
    opportunities = await source.fetch(_EPOCH)
    assert all(o.provenance.extraction_confidence >= 0.5 for o in opportunities)
    assert all(h.extraction_confidence < 0.5 for h in sink.held)
