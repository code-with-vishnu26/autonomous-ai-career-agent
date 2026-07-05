# ADR-0038: The Decide layer — deterministic ranking inside the Planner boundary

- **Status:** Accepted
- **Date:** 2026-07-04
- **References:** [ADR-0007](0007-planner-agent.md) (Decide as a swappable
  step, first implemented here), [ADR-0034](0034-ats-score-gate.md) (the
  keyword machinery reused unforked), [ADR-0013](0013-held-candidate-mechanism.md)
  (the visible-discard-pile discipline applied to excluded opportunities)

## Decision

`DeterministicDecideScorer` (`agents/planner/decide.py`): weighted
deterministic rank — profile match 50% (Phase 10's exact
`extract_jd_keywords` + `classify_missing_keywords`, unforked, per the
standing brief's "no new algorithm"; one vocabulary across Decide and the
ATS gate means Decide never ranks up a job the gate would then refuse),
source reliability 20% (authoritative ATS/API > YC > aggregator boards >
HN extraction > web search — ADR-0012's confidence ordering applied to
ranking), freshness 20% (7d/30d tiers; unknown dates score a neutral 50,
never fresh, never stale), salary transparency bonus 10% (the posting
visibly discusses pay — a regex presence check, never a parsed number).

**Config filters are hard excludes with named reasons** (`DecideFilters`:
blacklist, location allow-list — remote postings pass it — remote-only),
never penalties: a penalty can be outweighed by a great keyword match, an
exclusion cannot. Injection-verified (blacklist-as-penalty was caught).
Excluded opportunities are returned with their reasons, never silently
dropped (ADR-0013's discipline). Ties break by id — fully deterministic.

**Zero LLM calls in v1** — any escalation is its own justified pre-brief.

**Salary floor deliberately absent, named**: `Opportunity` has no
structured salary field, and parsing floors from prose is a confident
guess this project refuses everywhere else. The transparency bonus is the
honest substitute; a floor filter becomes possible only if a structured
field is added (revisit criterion).

`career-agent discover --profile <path>` now prints the ranked summary
(top 10 with scores + every exclusion with reasons); filters come from
Settings (`decide_blacklist_companies`/`decide_allowed_locations`/
`decide_remote_only`).

## Future revisit criteria

- A structured salary field lands on `Opportunity` → build the floor
  filter then.
- Repost detection beyond dedup (same job re-posted with a new native id)
  shows up in real data → extend freshness with dedup-history awareness.
- Real usage shows the deterministic rank mis-ordering in ways keyword
  coverage can't express → that is the LLM-escalation pre-brief trigger.
