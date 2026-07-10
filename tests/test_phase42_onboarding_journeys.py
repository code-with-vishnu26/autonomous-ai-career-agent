"""Phase 42: fresh-machine onboarding-journey guards.

Phase 42 revalidated the whole zero-to-first-run path end to end (editable
install, wheel install, and the ``setup`` readiness state matrix across the
no-key / key-present / no-artifact / artifact-present journeys) against
freshly built, independently installed artifacts. Almost everything was
already correct and already guarded by ``test_setup_command.py`` and
``test_phase39_onboarding_docs.py``.

The one real finding was a documentation-accuracy defect: the README
introduced its work-entry example with the words "a scaffolded work entry
looks like", but the actual scaffold (:func:`example_profile_dict`) emits a
*different* entry (``work-1``/``Example Company``/``startDate`` only, no
``endDate``) than the README showed (``w1``/``Acme Corp`` with an
``endDate``). The example loads correctly through the real loader -- so it
was never *broken* -- but the framing falsely claimed to be the literal
scaffold output. Phase 42 reworded it to "An example work entry ... looks
like" (illustrative, which it is), and these tests lock in both that the
prose no longer over-claims and that the README example and the real
scaffold can never drift apart on the two conventions that actually trip a
new user: the camelCase ``startDate`` key and the required ``id`` extension.

No live call; no network.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from career_agent.storage.profile import (
    example_profile_dict,
    load_master_profile,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _readme() -> str:
    return (_REPO_ROOT / "README.md").read_text(encoding="utf-8")


def _extract_readme_work_entry() -> dict:
    match = re.search(
        r'```json\n(\{.*?"highlights".*?\})\n```', _readme(), re.DOTALL
    )
    assert match is not None, "README's example work-entry JSON block not found"
    return json.loads(match.group(1))


def test_readme_does_not_claim_its_example_is_the_literal_scaffold_output() -> (
    None
):
    """The README's example differs from the real scaffold in every value;
    it must be framed as an illustrative example, not misdescribed as the
    literal output of ``career-agent setup``."""
    # Collapse whitespace so a line-wrapped phrase still matches.
    readme = " ".join(_readme().split())
    # The old, inaccurate framing must not reappear.
    assert "a scaffolded work entry looks like" not in readme
    # It must still be presented as an example, not the literal scaffold.
    assert "An example work entry" in readme


def test_readme_example_and_real_scaffold_agree_on_the_conventions_that_matter() -> (
    None
):
    """Cross-check the two independent sources of the profile shape. They may
    legitimately differ in placeholder values, but must never diverge on the
    camelCase ``startDate`` key or the required ``id`` extension -- the exact
    two things that silently break a new user's first ``apply`` (the Phase
    36/39 trap)."""
    readme_entry = _extract_readme_work_entry()
    scaffold_entry = example_profile_dict()["work"][0]

    for entry, label in ((readme_entry, "README"), (scaffold_entry, "scaffold")):
        assert "startDate" in entry, f"{label} must use camelCase startDate"
        assert "start_date" not in entry, f"{label} must not use snake_case"
        assert str(entry.get("id", "")).strip(), f"{label} entry needs an id"


def test_the_actual_scaffold_loads_through_the_real_cli_loader() -> None:
    """The exact bytes ``career-agent setup`` writes must load through
    ``load_master_profile`` (the path ``apply`` uses), not merely through a
    raw ``MasterProfile.model_validate`` that bypasses the camelCase
    mapping."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "profile.json"
        path.write_text(
            json.dumps(example_profile_dict()), encoding="utf-8"
        )
        profile = load_master_profile(path)

    work = profile.work[0]
    # camelCase startDate on disk -> parsed date on the snake_case field.
    assert work.start_date is not None
    assert work.end_date is None  # scaffold omits endDate (a current role)
    assert profile.education[0].study_type == "BSc"  # studyType -> study_type
