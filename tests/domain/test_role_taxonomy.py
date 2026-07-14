"""Tests for the curated tech-role taxonomy (Phase 72, ADR-0090)."""

from __future__ import annotations

from career_agent.domain.role_taxonomy import ROLE_FAMILIES, expand_role


def test_unknown_role_returns_an_empty_not_known_expansion() -> None:
    expansion = expand_role("professional dog walker")
    assert not expansion.is_known
    assert expansion.matched_families == frozenset()
    assert expansion.synonym_terms == frozenset()
    assert expansion.related_terms == frozenset()


def test_blank_query_returns_an_empty_expansion() -> None:
    expansion = expand_role("   ")
    assert not expansion.is_known


def test_junior_software_developer_widens_seniority_and_finds_related_roles() -> None:
    expansion = expand_role("junior software developer")
    assert expansion.is_known
    assert "software developer" in expansion.matched_families
    # Seniority widening -- catches postings titled "entry level" etc.
    assert "entry level" in expansion.synonym_terms
    assert "associate" in expansion.synonym_terms
    # Exact-match synonyms include the family's own alternate spellings.
    assert "software engineer" in expansion.synonym_terms
    # Related sub-roles are surfaced, e.g. backend/cloud/devops.
    assert "backend developer" in expansion.related_family_names
    assert "cloud engineer" in expansion.related_family_names
    assert any("backend" in term for term in expansion.related_terms)


def test_related_terms_never_overlap_synonym_terms() -> None:
    for family in ROLE_FAMILIES:
        expansion = expand_role(family)
        assert expansion.synonym_terms.isdisjoint(expansion.related_terms)


def test_related_family_names_never_include_the_matched_family_itself() -> None:
    expansion = expand_role("backend developer")
    assert "backend developer" in expansion.matched_families
    assert "backend developer" not in expansion.related_family_names


def test_acronym_matches_whole_word_only() -> None:
    # "sre" must not accidentally match inside an unrelated word like "misread".
    expansion = expand_role("we misread the requirements")
    assert not expansion.is_known
    expansion = expand_role("site reliability engineer (SRE)")
    assert "site reliability engineer" in expansion.matched_families


def test_every_related_family_name_is_a_real_taxonomy_entry() -> None:
    for family in ROLE_FAMILIES.values():
        for related in family.related:
            assert related in ROLE_FAMILIES, (
                f"{family.canonical} -> unknown {related!r}"
            )


def test_no_family_lists_itself_as_related() -> None:
    for family in ROLE_FAMILIES.values():
        assert family.canonical not in family.related


def test_data_scientist_relates_to_data_and_ml_engineering() -> None:
    expansion = expand_role("data scientist")
    assert "data engineer" in expansion.related_family_names
    assert "machine learning engineer" in expansion.related_family_names


def test_senior_qa_engineer_matches_qa_family_and_widens_senior_synonyms() -> None:
    expansion = expand_role("Senior QA Engineer")
    assert "qa engineer" in expansion.matched_families
    assert "staff" in expansion.synonym_terms
    assert "lead" in expansion.synonym_terms
