"""Guard: .env.example must never carry a real-looking secret value.

Real incident (2026-07-11): a real Groq API key was accidentally committed
directly into the tracked `.env.example` template (meant to be a
placeholder-only file copied to a real, git-ignored `.env`). Nothing
previously checked the *content* of `.env.example` -- only that the
filename itself isn't treated as a forbidden packaging entry
(`test_phase35_ci_release_tooling.py`). This guard closes that gap: every
`*_API_KEY`/`*_TOKEN`/`*_SECRET`-shaped line in the committed template must
be empty, never a real-looking value. It does not (and cannot) undo a
leak already present in git history -- only rotating the exposed
credential does that.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SECRET_LINE = re.compile(
    r"^(?P<key>[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)=(?P<value>.*)$"
)
# *_PATH fields (e.g. GMAIL_TOKEN_PATH) name a *file location*, not a secret
# value -- a non-empty default path is normal and not a leak.
_PATH_FIELD = re.compile(r"_PATH$")


def test_env_example_secret_fields_are_all_empty_placeholders() -> None:
    text = (_REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    offenders = []
    for line in text.splitlines():
        match = _SECRET_LINE.match(line.strip())
        if not match:
            continue
        if _PATH_FIELD.search(match.group("key")):
            continue
        if match.group("value").strip():
            offenders.append(line)
    assert not offenders, (
        f".env.example must never carry a real-looking secret value, only "
        f"an empty placeholder: {offenders}"
    )
