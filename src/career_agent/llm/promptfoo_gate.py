"""Positive verification that promptfoo has actually passed (ADR-0016, ADR-0026).

ADR-0016 requires the promptfoo suite to pass on live calls before
``AnthropicClaimVerifier`` is wired into any real apply path. That
requirement was, until now, enforced only by written policy plus the
import-linter contract keeping the concrete class out of ``agents``/
``core``/``plugins``/``storage`` -- ``cli.py`` is deliberately the one place
allowed to construct it (it is the composition root), which means nothing
structural stopped a real, unvalidated verifier from being wired in at
exactly the point it would first matter.

``verify_promptfoo_results`` closes that gap the same way this project
closes every other one: check the evidence, not the claimed verdict. A CLI
flag someone types from memory ("I promise I ran it") is exactly the kind
of unverified assertion the truthfulness gate itself refuses to accept from
a claimed confidence score -- so this checks an actual results artifact on
disk instead, tied to the exact prompt version it validated by filename, and
verifies its recorded pass/fail counts, not merely that the file exists.
"""

from __future__ import annotations

import json
from pathlib import Path


class PromptfooNotValidatedError(Exception):
    """No passing promptfoo results artifact was found for this prompt version.

    Raised instead of trusting an assertion -- the same "check the
    evidence, not the claimed verdict" discipline the truthfulness gate
    itself is built on, now applied to whether the gate's own real
    implementation has actually been validated.
    """


def verify_promptfoo_results(prompt_version: str, results_dir: Path) -> None:
    """Raise unless ``results_dir / f"{prompt_version}.json"`` proves a pass.

    The filename convention ties a results artifact to the exact prompt
    version it validated -- a stale pass from a since-changed prompt has a
    different filename and will not be found here. Checks the file's
    actual recorded pass/fail counts (``results.stats.successes``/
    ``failures``, the shape ``promptfoo eval -o <file>`` writes), not
    merely that the file exists or that it once existed.
    """
    results_path = results_dir / f"{prompt_version}.json"
    if not results_path.exists():
        raise PromptfooNotValidatedError(
            f"No promptfoo results found for prompt version {prompt_version!r} "
            f"at {results_path}. Run the promptfoo suite on your own machine "
            f"(real network + ANTHROPIC_API_KEY required -- see "
            f"promptfoo/README.md) and write its output there:\n"
            f"  npx promptfoo@latest eval --config "
            f"promptfoo/promptfooconfig.yaml -o {results_path}"
        )
    try:
        payload = json.loads(results_path.read_text())
        stats = payload["results"]["stats"]
        failures = int(stats["failures"])
        successes = int(stats["successes"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise PromptfooNotValidatedError(
            f"{results_path} exists but could not be read as a valid "
            f"promptfoo results file: {exc}"
        ) from exc
    if successes == 0 or failures != 0:
        raise PromptfooNotValidatedError(
            f"{results_path} records {successes} passing and {failures} "
            f"failing case(s) -- the promptfoo suite has not fully passed "
            f"for prompt version {prompt_version!r}."
        )
