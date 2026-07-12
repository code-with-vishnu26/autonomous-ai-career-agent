"""Career Coach: advisory-only candidate-strengthening features (Phase 57, ADR-0075).

Six of the ten features named in the Phase 57 brief have a real data
source in this codebase and are built here: Resume Analysis, Job Match
Score, AI Resume Suggestions, Cover Letter Assistant, Interview
Preparation, and Skill Gap Analysis. Four (Company Research, Salary
Insights, Weekly Career Report, Career Roadmap) do not -- see ADR-0075 for
why each is explicitly deferred rather than faked.

Every module here holds to four hard constraints (Phase 57's own "AI
principles"): never fabricate achievements, suggestions are advisory only,
nothing is ever applied without explicit user acceptance, and every
suggestion explains why it was made.
"""

from __future__ import annotations
