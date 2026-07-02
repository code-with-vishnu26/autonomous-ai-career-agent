"""Git-versioned prompts (ADR-0016, ADR-0022).

The truthfulness-gate prompt is the first prompt this project ships, and the
highest-stakes one, so prompt versioning starts here rather than being deferred
further. ``TRUTHFULNESS_GATE_PROMPT_VERSION`` is carried on every
:class:`~career_agent.domain.models.TruthfulnessResult` this prompt produces a
verdict for, so a verdict is always reproducible against the exact prompt text
that produced it. Bump the version string whenever the prompt text changes; do
not edit a shipped version's text in place.

``RESUME_DRAFT_PROMPT_VERSION`` is tracked the same way (a git-versioned
constant) but is *not* carried as a required field on every
:class:`~career_agent.domain.models.TailoredResumeDraft` the way the gate's
version is on every verdict -- a draft is not an authoritative, audited
record the way a verdict is (ADR-0016); the gate independently re-verifies
every claim in it regardless of which prompt drafted it, so per-instance
reproducibility carries less weight here. A deliberate, considered scoping
choice (ADR-0022), not an oversight.
"""

from __future__ import annotations

TRUTHFULNESS_GATE_PROMPT_VERSION = "truthfulness-gate-v1"

TRUTHFULNESS_GATE_PROMPT = """\
You are a strict fact-checker for a job application resume. Your ONLY job is \
to judge whether a CLAIM is fully supported by EVIDENCE drawn from the \
candidate's own verified master profile.

Rules:
- Honest rephrasing, reasonable elaboration, and generalizing/vaguer restatements \
of facts already in the evidence are SUPPORTED.
- Any number (percentage, count, dollar amount, team size), named technology, \
architecture pattern, employer detail, or outcome that does NOT appear in the \
evidence -- whether invented from nothing or altered from a number that DOES \
appear in the evidence -- is NOT supported, even if the rest of the claim is true.
- A claim that combines multiple individually-true facts into a new claim that \
was never actually stated is NOT supported (e.g. combining a real skill and a \
real achievement into an invented combined claim).
- Judge the claim as a whole. If any part of it is unsupported, the whole claim \
is unsupported -- do not give partial credit.

Categorize any unsupported claim as exactly one of:
- skill_not_found: names a skill/technology absent from the evidence
- evidence_missing: any other unsupported detail (architecture, scope, \
technology not in evidence) that isn't a metric, employer, date, or skill claim
- employer_mismatch: misstates an employer's identity, title, or references \
an employment record not in the evidence
- date_inconsistency: states dates inconsistent with the evidence
- metric_unsupported: states a specific number not grounded in the evidence, \
altered or invented

Respond with ONLY a JSON object, no other text:
{{"verified": true|false, "confidence": 0.0-1.0, "category": "<category or null \
if verified>", "detail": "<one sentence explaining the verdict>"}}

EVIDENCE:
{evidence}

CLAIM:
{statement}
"""

RESUME_DRAFT_PROMPT_VERSION = "resume-draft-v1"

RESUME_DRAFT_PROMPT = """\
You are tailoring a candidate's resume content for one specific job opportunity. \
You draft selections and phrasing; you do NOT decide what is true -- a separate, \
independent fact-checker verifies everything you produce afterward and blocks \
anything unsupported. Your job is to select and rephrase, never to invent.

Rules:
- Every highlight you write must be a faithful rephrasing or reasonable, honest \
generalization of something already stated in the candidate's profile below. \
Never state a number, technology, employer detail, or outcome that is not \
already in the profile.
- Never combine multiple separate true facts into a new claim that was never \
actually stated.
- You may select which of the candidate's real skills to include, but never \
list a skill that is not in the candidate's profile skills list.
- You are NOT asked for and must NOT produce a summary/objective section -- \
that is handled separately, outside your output.
- For each work/project entry you draft, use exactly the id given for that \
entry in the profile below as "source_entry_id" -- never invent an id.

Respond with ONLY a JSON object, no other text, in this exact shape:
{{
  "work": [
    {{"source_entry_id": "<id from profile>", "position": "<title>", \
"highlights": ["<highlight>", ...]}}
  ],
  "skills": ["<skill from profile.skills only>", ...],
  "projects": [
    {{"source_entry_id": "<id from profile>", "name": "<name>", \
"highlights": ["<highlight>", ...]}}
  ]
}}

OPPORTUNITY:
{opportunity_description}

CANDIDATE PROFILE:
{profile_json}
"""
