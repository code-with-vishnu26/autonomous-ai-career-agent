"""Tests for career_agent.domain.identity -- the dedup backbone."""

from __future__ import annotations

from career_agent.domain.identity import (
    canonical_fingerprint,
    normalize,
    opportunity_id,
)


def test_normalize_is_case_punctuation_and_whitespace_insensitive() -> None:
    assert normalize("  Senior  Back-End Engineer! ") == "senior back end engineer"
    assert normalize("") == ""


def test_fingerprint_is_source_independent() -> None:
    """The same real role discovered two different ways -- once from Greenhouse
    (company = board token) and once from a career page -- must produce the
    SAME fingerprint, because it is built only from company/title/location and
    never from any ATS-internal id. This is the property 4c depends on."""
    from_greenhouse = canonical_fingerprint(
        company="Acme", title="Senior Backend Engineer", location="Remote - US"
    )
    from_career_page = canonical_fingerprint(
        company="  acme  ", title="senior backend engineer", location="remote - us"
    )
    assert from_greenhouse == from_career_page


def test_fingerprint_distinguishes_different_roles() -> None:
    engineer = canonical_fingerprint("Acme", "Backend Engineer", "Remote")
    designer = canonical_fingerprint("Acme", "Product Designer", "Remote")
    assert engineer != designer


def test_opportunity_id_prefers_ats_identity_and_is_stable() -> None:
    kwargs = dict(
        ats_kind="greenhouse",
        board_token="acme",
        ats_ref="4012345",
        company="acme",
        title="Senior Backend Engineer",
        location="Remote - US",
    )
    first = opportunity_id(**kwargs)
    second = opportunity_id(**kwargs)
    assert first == second  # deterministic


def test_two_reqs_sharing_a_title_do_not_over_merge() -> None:
    """Distinct Greenhouse reqs with identical title/location but different job
    ids must get different ids -- the ATS identity prevents over-merging that a
    pure title fingerprint would cause."""
    a = opportunity_id(
        ats_kind="greenhouse",
        board_token="acme",
        ats_ref="1",
        company="acme",
        title="Software Engineer",
        location="Remote",
    )
    b = opportunity_id(
        ats_kind="greenhouse",
        board_token="acme",
        ats_ref="2",
        company="acme",
        title="Software Engineer",
        location="Remote",
    )
    assert a != b


def test_opportunity_id_falls_back_to_fingerprint_without_ats_identity() -> None:
    """With no ATS id (e.g. a raw career-page find), the id is derived from the
    source-independent fingerprint, so an ATS-less duplicate of a known role
    still has a stable identity."""
    no_ats = opportunity_id(
        ats_kind=None,
        board_token=None,
        ats_ref=None,
        company="Acme",
        title="Senior Backend Engineer",
        location="Remote - US",
    )
    same_again = opportunity_id(
        ats_kind=None,
        board_token=None,
        ats_ref=None,
        company="acme",
        title="senior backend engineer",
        location="remote - us",
    )
    assert no_ats == same_again
