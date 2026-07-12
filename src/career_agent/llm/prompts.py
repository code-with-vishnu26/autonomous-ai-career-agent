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

TRUTHFULNESS_GATE_PROMPT_VERSION = "truthfulness-gate-v2"

#: Tracks the Career Coach's free-text advisor port (Phase 57, ADR-0075).
#: Unlike the other constants here, this is not one fixed prompt template --
#: ``CareerCoachAdvisor.draft_text`` takes an arbitrary caller-built prompt --
#: so this version tracks the *port's contract* (model, call shape), bumped
#: whenever that changes, not a single prompt's text.
COACH_ADVISOR_PROMPT_VERSION = "coach-advisor-v1"

TRUTHFULNESS_GATE_PROMPT = """\
You are a strict fact-checker for a job application resume. Your ONLY job is \
to judge whether a CLAIM is fully supported by EVIDENCE drawn from the \
candidate's own verified master profile.

Rules:
- Honest rephrasing, reasonable elaboration, and generalizing/vaguer restatements \
of facts already in the evidence are SUPPORTED -- but ONLY when they introduce \
no new technology, no new number, no new seniority/title word, and no stronger \
action verb than the evidence itself uses (see the next two rules).
- A technology or skill named ONLY in a bare skills list, with no evidence it was \
ever actually used to do anything, does NOT by itself support a claim that an \
ACTION was performed with it. "Docker" in a skills list supports "the candidate \
knows Docker" -- it does NOT support "containerized services using Docker" \
unless the evidence separately shows Docker being used for something. The same \
applies to competency nouns ("database design", "system architecture") standing \
in for an unstated verb.
- A stronger ownership/action verb is NOT automatically entailed by a weaker one \
for the same object, even when the object and the rest of the claim are true. \
"architected"/"led"/"owned"/"directed" are NOT interchangeable with \
"built"/"used"/"worked on"/"improved" -- claiming the former where the evidence \
only shows the latter is an unsupported escalation, not a stylistic rephrase.
- Any number (percentage, count, dollar amount, team size), named technology, \
architecture pattern, employer detail, seniority/title word, or outcome that \
does NOT appear in the evidence -- whether invented from nothing or altered \
from a number that DOES appear in the evidence -- is NOT supported, even if the \
rest of the claim is true.
- A claim that combines multiple individually-true facts into a new claim that \
was never actually stated is NOT supported (e.g. combining a real skill and a \
real achievement into an invented combined claim).
- Judge the claim as a whole. If any part of it is unsupported, the whole claim \
is unsupported -- do not give partial credit.

Categorize any unsupported claim as exactly one of:
- skill_not_found: names a skill/technology absent from the evidence entirely
- evidence_missing: any other unsupported detail (architecture, scope, \
technology not in evidence) that isn't a metric, employer, date, skill, \
seniority, or action-inference claim
- employer_mismatch: misstates an employer's identity, or references an \
employment record not in the evidence
- date_inconsistency: states dates inconsistent with the evidence
- metric_unsupported: states a specific number not grounded in the evidence, \
altered or invented
- unsupported_seniority: claims a title/seniority word (e.g. "Senior", "Lead", \
"Director") absent from the evidenced position
- unsupported_action_inference: claims a stronger action/ownership verb than \
evidenced for the same object, OR pairs an action/competency word with a \
technology that is only ever a bare skills-list entry, never demonstrated

Respond with ONLY a JSON object, no other text:
{{"verified": true|false, "confidence": 0.0-1.0, "category": "<category or null \
if verified>", "detail": "<one sentence explaining the verdict>"}}

EVIDENCE:
{evidence}

CLAIM:
{statement}
"""

RESUME_DRAFT_PROMPT_VERSION = "resume-draft-v2"

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
{gap_section}"""

# Appended to RESUME_DRAFT_PROMPT only on an ATS-gate retailor attempt
# (Phase 10, ADR-0034). The keyword list interpolated here comes from an
# AtsGapReport, a type that structurally can only carry keywords the
# candidate's profile actually evidences (SURFACEABLE) -- a keyword with no
# profile support can never appear below, so this instruction can never
# name a fabrication target.
RESUME_DRAFT_GAP_SECTION = """
RETAILORING FOCUS -- the previous draft under-surfaced these skills, each of
which IS genuinely present in the candidate's profile (supporting evidence
shown). Surface each one ONLY where the profile genuinely supports it --
never invent, never exaggerate, never add a skill beyond what the evidence
states:
{surfaceable_lines}
"""

SEMANTIC_KEYWORD_PROMPT_VERSION = "semantic-keyword-v1"

# The ATS gate's advisory semantic layer (Phase 10, ADR-0034). The model's
# answer is never trusted directly: every quoted_phrase is re-verified as a
# literal substring of the resume text by verified_semantic_keywords()
# before it prunes anything, and nothing it produces can reach the gate's
# pass/fail decision (matrix cases A1/A3).
SEMANTIC_KEYWORD_PROMPT = """\
A resume is being checked against a job description's required keywords. \
For each keyword listed below that is NOT literally present in the resume, \
decide whether the SAME CONCEPT is genuinely present under different wording.

Rules:
- Only claim a match when the resume genuinely demonstrates the concept -- \
plausible association is not enough ("containerization" alone does NOT \
demonstrate "Kubernetes"; a generic "cloud" mention does NOT demonstrate \
"AWS").
- For every match you claim, quote the EXACT phrase from the resume that \
demonstrates it, verbatim, character-for-character. Claims whose quoted \
phrase does not appear literally in the resume are discarded automatically.
- If no keyword is genuinely present under different wording, return an \
empty list. That is a normal, expected answer.

Respond with ONLY a JSON array, no other text:
[{{"keyword": "<keyword from the list>", "quoted_phrase": "<verbatim phrase \
from the resume>"}}]

MISSING KEYWORDS:
{missing_keywords}

RESUME TEXT:
{resume_text}
"""
