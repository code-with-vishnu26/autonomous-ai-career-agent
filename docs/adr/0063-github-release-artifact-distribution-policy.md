# ADR-0063: GitHub Releases carry source archives only (no binary assets), and v1.1.0 post-release reconciliation (Phase 45)

- **Status:** Accepted
- **Date:** 2026-07-10
- **References:** ADR-0056 (v1 prepare-only release scope), ADR-0059
  (v1.0.0 promotion), ADR-0061 (packaging hardening + `verify_release_artifacts.py`),
  ADR-0062 (v1.1 readiness audit + SemVer decision)

## Context

After the v1.1.0 promotion PR (#66) merged, the maintainer manually created
and pushed the annotated `v1.1.0` tag and manually published a GitHub
Release. Phase 45 reconciled the repository against that now-real release
state and had to answer one decision ADR-0062 did not: **the GitHub Release
exists but has no attached assets — should freshly built binary artifacts
(wheel + sdist) be attached to it?**

Verified reality (Phase 45):

- **Tag integrity.** `v1.1.0` is an annotated tag; its object is
  `081505062acc5eed8c603d8aa8ee0807de662905` and it peels to commit
  `a563dbe4628f5a0df186a4ce9fd3a1e6958d5256` — the Phase 44 merge commit and
  the current `origin/main` head. Local tag object, remote tag object
  (`git ls-remote`), and the peeled commit all agree, and match the
  owner-observed evidence. The immutable `v1.0.0` tag is unchanged (object
  `0ddcda04…`; peeled commit `b8414e3…`).
- **GitHub Release.** Verified directly through the GitHub API
  (`get_release_by_tag`): id `352138767`, name "Autonomous AI Career Agent
  v1.1.0", `draft=false`, `prerelease=false`,
  `published_at=2026-07-10T14:14:01Z`, `target_commitish=a563dbe…`. Assets:
  none.
- **Artifacts build cleanly** from the released source (`a563dbe…`):
  `career_agent-1.1.0-py3-none-any.whl` (86 entries) and
  `career_agent-1.1.0.tar.gz` (288 entries), no forbidden content, wheel
  smoke passes, no `rc`/`dev`/`1.0.0` residue.

## Decision

**GitHub Releases for this project publish source archives only — no binary
wheel/sdist assets are attached (`KEEP_SOURCE_ARCHIVES_ONLY`).** Every
GitHub Release automatically carries a source zipball/tarball; that is the
published artifact. Freshly built wheels/sdists are verification evidence,
not published deliverables.

Rationale:

1. **It matches the already-documented, test-enforced install policy.** The
   README states, and `test_phase39_onboarding_docs.py` pins, that "there is
   no PyPI package and no published GitHub Release asset yet" and that
   **editable install from a cloned checkout is the only verified path.**
   Attaching binaries would contradict that stance and would require a
   coordinated README + test change — a distribution-policy change, not a
   reconciliation.
2. **Provenance discipline.** A wheel built in this Linux sandbox cannot be
   claimed byte-for-byte reproducible against a maintainer build; publishing
   it as *the* v1.1.0 binary would assert a provenance the project does not
   establish. `verify_release_artifacts.py` proves *content hygiene*, not
   build reproducibility.
3. **Least-surprise for a single-user, self-hosted tool.** The audience
   clones and installs editable; a binary asset invites `pip install`
   patterns the project explicitly does not yet verify.

Attaching binary assets in the future is a deliberate, separate decision
that must supersede this ADR (and update the README + Phase 39 guard), not
something done ad hoc because a build happens to exist.

## Post-release documentation reconciliation

Because `docs/release/v1.1.0-notes.md` and the README Status section were
written *before* the tag/Release existed, they carried pre-release wording
("Promotion prepared", "pending owner authorization", a "run this manually"
tag block, and a README Status still announcing v1.0.0). Phase 45 corrected
them to the released reality and drew an explicit line between:

- **software release state = `RELEASED`** (tag + GitHub Release exist), and
- **product safety posture = `PREPARE_ONLY`** (the tool never submits to any
  external system).

These are independent: a released piece of software can still be
prepare-only by design. The correction does **not** rewrite ADR-0062, the
historical v1.0.0 notes, or Phase 43/44 history — those recorded what was
true at their decision time; a dated post-release reconciliation section
records what became true afterward.

## What this ADR does not change

- No version bump (stays `1.1.0`; Phase 45 shipped no runtime-code change).
- No safety-posture change: `executor_available=False` is still hardcoded,
  no `Applicator` is constructed in the CLI, external submission remains
  unreachable, and zero submissions were performed.
- No tag mutation: neither `v1.0.0` nor `v1.1.0` is moved, deleted, or
  force-pushed by this repository or by the agent.

## Consequences

- `docs/release/v1.1.0-notes.md` and `README.md` Status/posture wording
  reconciled to released reality.
- New `tests/test_phase45_post_release_reconciliation.py` guards the
  corrected wording and the RELEASED-vs-PREPARE_ONLY distinction; the one
  Phase 44 guard that asserted the (now-removed) "pending" wording was
  updated in lockstep to assert the released state.
- The published GitHub Release *body* still shows the pre-reconciliation
  text (it was copied from the notes at publication time). Editing a
  published, public Release is an outward-facing action left to the
  maintainer's explicit choice; the authoritative, reconciled notes live in
  the repository.

## Future revisit criteria

Revisit if the project decides to publish to PyPI or to attach verified
binary assets to Releases — either would supersede the
`KEEP_SOURCE_ARCHIVES_ONLY` decision and require updating the README install
policy and its Phase 39 guard in the same change.
