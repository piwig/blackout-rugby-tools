# Affiliates and selections implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development. Steps use checkbox syntax for tracking.

**Goal:** Repair reproduced imports and selection navigation failures.
**Architecture:** Preserve current per-manager SQLite stores and namespaced team identities. Correct source routing and expose supported capabilities in the existing React views.
**Tech Stack:** Python/FastAPI/SQLite, React/TypeScript, pytest and Node tests.
**Spec:** ../specs/2026-11-01-affiliates-selections-design.md

## Global Constraints

Private per-manager data; no game writes; preserve club/U20/NT namespaces, drafts and concurrency checks. FR/EN/ES/IT. Synthetic tests only. No private account data in Git.

## Review Focus

- Generic ODS metadata and plans must follow its chosen club, not only player rows.
- Explicit empty API responses differ from missing/malformed players.
- Identical data read later is fresh but must not fabricate a skill gain.
- Suspended selections must retain local analysis and history.
- Club users keep their existing calendar import and academy controls.

## Task 1: import and observation integrity

Files: server/imports.py, storage.py, main.py and freshness consumers as necessary; tests/test_imports.py, test_api.py, test_workbench.py and focused regression tests.

- [ ] Reproduce generic ODS target, empty targeted sync, unchanged observation freshness with failing tests.
- [ ] Apply minimal fixes preserving documented historical ODS formats and actual observation history.
- [ ] Verify malformed responses preserve data; multiple contexts remain isolated; report test results.

## Task 2: selection-aware interface

Files: web/src/selection-dashboard.tsx, workbench.tsx, progression.tsx, pages.tsx, optimization.tsx, App.tsx, translation catalog and relevant Node tests.

- [ ] Pin suspended selection controls and unsupported calendar/academy controls with failing rendered tests.
- [ ] Show clear selection state, retain manual calendar, add DailyHub and grouped team choices, correct club/selection terminology.
- [ ] Verify club and selection states plus translations and production build.

## Task 3: review and release

- [ ] Review both diffs independently, resolve findings and run full Python/Node suites, translation checker and build.
- [ ] Visually verify synthetic affiliated-club/U20/NT contexts, including suspended selection.
- [ ] Commit, update public GitHub and deploy approved standing scope with backup and rollback; check health/auth/static assets.
- [ ] Record BRM observations separately in private review, distinguish features inspected from data/calculations not yet verified.
