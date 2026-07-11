"""Generic, platform-agnostic required-field detection/triage (ADR-0028/0032).

Extracted from :mod:`career_agent.agents.apply.browser_applicator` (Phase
51, ADR-0069) without behavior change -- these functions never depended on
anything ``BrowserApplicator``-specific, only on a live Playwright ``Page``
and a ``FormFiller``'s declared ``known_field_selectors``. Giving them their
own home is what lets a second caller (the new
:class:`~career_agent.agents.application.engine.ApplicationPreparationEngine`,
Phase 51) reuse the exact same detection/classification/auto-fill logic
``BrowserApplicator`` already proved, instead of re-implementing it --
the same "extract and share, don't duplicate" move Phase 47 made for
``BrowserManager``/``SessionManager`` out of this same file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from career_agent.agents.apply.question_answerer import (
    AmbiguousQuestionError,
    MissingLegalStatusFactError,
    QuestionCategory,
    answer_factual_question,
    classify_question,
    match_dropdown_option,
)
from career_agent.domain.models import LegalStatusSection

if TYPE_CHECKING:
    from playwright.async_api import ElementHandle, Page


class ManifestField(NamedTuple):
    """One required field that could not be auto-resolved, for a human's reference."""

    selector: str
    category: str
    question_text: str


async def required_unknown_elements(
    page: Page, known_field_selectors: frozenset[str]
) -> list[tuple[str | None, ElementHandle, str | None]]:
    """Every required form element not a known submit-mechanic or FormFiller field.

    Each triple is ``(selector, element, element_id)`` -- ``selector`` is
    ``None`` only when the element has neither ``id`` nor ``name`` to
    derive one from.
    """
    elements = await page.query_selector_all("form input, form textarea, form select")
    result: list[tuple[str | None, ElementHandle, str | None]] = []
    for element in elements:
        input_type = (await element.get_attribute("type")) or ""
        if input_type.lower() in {"submit", "button", "hidden"}:
            continue
        if await element.get_attribute("required") is None:
            continue
        element_id = await element.get_attribute("id")
        name = await element.get_attribute("name")
        if element_id:
            selector = f"#{element_id}"
        elif name:
            selector = f"[name='{name}']"
        else:
            selector = None
        if selector is not None and selector in known_field_selectors:
            continue
        result.append((selector, element, element_id))
    return result


async def unhandled_required_fields(
    page: Page, known_field_selectors: frozenset[str]
) -> list[str]:
    """Return every required form field a FormFiller doesn't know how to fill.

    Queried generically against the real page's actual ``form`` elements
    (not a fixed per-platform list), so this works the same way regardless
    of which ATS's form is loaded.
    """
    fields = await required_unknown_elements(page, known_field_selectors)
    return [
        selector if selector is not None else "(no id or name)"
        for selector, _element, _element_id in fields
    ]


async def field_question_text(
    page: Page, element: ElementHandle, element_id: str | None
) -> str:
    """The best available human-readable text describing this field.

    Tries ``aria-label``, then an associated ``<label for="...">``, then
    ``placeholder``, in that order -- the same priority a screen reader
    would use.
    """
    aria_label = await element.get_attribute("aria-label")
    if aria_label and aria_label.strip():
        return aria_label.strip()
    if element_id:
        label = await page.query_selector(f"label[for='{element_id}']")
        if label is not None:
            text = await label.inner_text()
            if text and text.strip():
                return text.strip()
    placeholder = await element.get_attribute("placeholder")
    if placeholder and placeholder.strip():
        return placeholder.strip()
    return ""


async def try_fill_boolean_select(element: ElementHandle, fact: bool) -> bool:
    """Fill a ``<select>`` from a resolved boolean fact, if it confidently maps.

    Deterministic, not a model call -- maps the fact to a "Yes"/"No"
    candidate string and reuses
    :func:`~career_agent.agents.apply.question_answerer.match_dropdown_option`
    against the live, enumerated ``<option>`` text. Returns ``False`` (never
    guesses, never fills) when the element isn't a ``<select>`` at all, or
    when nothing on the real page clears the match threshold.
    """
    tag = await element.evaluate("el => el.tagName.toLowerCase()")
    if tag != "select":
        return False
    option_elements = await element.query_selector_all("option")
    options: list[str] = []
    for option_element in option_elements:
        text = (await option_element.inner_text()).strip()
        if text:
            options.append(text)
    candidate = "Yes" if fact else "No"
    result = match_dropdown_option(candidate, options)
    if result.matched_option is None:
        return False
    await element.select_option(label=result.matched_option)
    return True


async def triage_unhandled_fields(
    page: Page,
    known_field_selectors: frozenset[str],
    legal_status: LegalStatusSection,
) -> tuple[list[str], list[ManifestField]]:
    """Classify every required-but-unknown field into auto-filled / manifest / refuse.

    A Category 2 (factual) field with an already-captured fact is filled
    automatically here and never appears in either returned list. Category
    1 (EEOC) and Category 3 (subjective) fields always land in the
    manifest. A field with no describable question text at all is returned
    in the first (hard-refuse) list instead of either the other two --
    handing a human a context-free blank field is close enough to guessing
    that outright refusal is the honest response.
    """
    hard_refuse: list[str] = []
    manifest: list[ManifestField] = []
    fields = await required_unknown_elements(page, known_field_selectors)
    for selector, element, element_id in fields:
        if selector is None:
            hard_refuse.append("(no id or name)")
            continue
        question_text = await field_question_text(page, element, element_id)
        if not question_text:
            hard_refuse.append(selector)
            continue

        category = classify_question(question_text)
        if category == QuestionCategory.FACTUAL:
            try:
                fact = answer_factual_question(question_text, legal_status)
            except (AmbiguousQuestionError, MissingLegalStatusFactError):
                manifest.append(
                    ManifestField(selector, category.value, question_text)
                )
                continue
            if await try_fill_boolean_select(element, fact):
                continue
            manifest.append(ManifestField(selector, category.value, question_text))
            continue

        manifest.append(ManifestField(selector, category.value, question_text))

    return hard_refuse, manifest


async def fields_still_empty(page: Page, selectors: tuple[str, ...]) -> list[str]:
    """Which of ``selectors`` are still empty on the live page right now.

    Queried freshly against the real page each time this is called, never
    cached or trusted from an earlier check.
    """
    empty: list[str] = []
    for selector in selectors:
        element = await page.query_selector(selector)
        if element is None:
            empty.append(selector)
            continue
        value = await element.input_value()
        if not value:
            empty.append(selector)
    return empty
