# Training Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import local Classic HTML/EML training reports into the private coaching notebook and explain their observed results without confusing sources or missing data.

**Architecture:** A bounded, offline Python parser returns the existing training-report shape with versioned optional metadata. A new local upload-preview route shares the notebook's atomic confirmation mechanism; immutable mail observations coexist with API reports. React derives per-report summaries and presents provenance, coverage, warnings and player details.

**Tech Stack:** FastAPI, SQLite private store, Python standard library HTMLParser/email, React/TypeScript, existing pytest and Node test suites.

**Spec:** `docs/superpowers/specs/2026-11-24-training-reports-design.md` (approved).

## Global Constraints

- Work only in the existing isolated checkout; no deployment, push, game write or email synchronization.
- No real account, mail, player or secret data in tracked source/tests/docs. Synthetic fixtures only; real-report validation stays in private excluded folders.
- No new dependency or remote service; no execution or fetching of imported HTML content.
- Formats v1: English Classic HTML and EML containing that HTML, including multipart, quoted-printable and base64. Reject text-only, ambiguous forwarded chains and unrecognized languages.
- Limits: 2 MiB raw and decoded, 50 MIME parts, depth 8, 200 players per phase, 10 distinct skills per player, normalized document 512000 bytes maximum.
- Local authenticated club authorization and exact Unicode/space-normalized club-name match; contradictory explicit club ID rejects. Historical absent players warn. Imported identity does not authenticate its sender.
- Preview does not write. Confirmation is atomic, owner/club/revision-bound. Mail import never requires Classic keys or calls.
- Immutable separate mail observations, normalized duplicate detection and visible shared-field disagreements. Never add several sources' gains together.
- Preserve legacy report readability and semantics; optional absent/null fields and schema version do not alone create an API conflict.
- Unknown is null; explicitly empty is []; no whole-level pop does not imply no progress. Text energy is not a numeric percentage or an inferred delta.
- No unsupported causal inference for CSR losses or conversion to complete player snapshots.
- All new product copy and help in the four existing languages.

## Review Focus

- A historical player absent from today's roster must remain importable with a warning; cross-club identity must reject (Task 1 routes).
- A multipart mail with several plausible reports must reject rather than select silently; remote HTML assets must never be fetched (Task 1 parser).
- Re-reading a legacy API observation after adding optional metadata must not falsely conflict; a real common-field contradiction must preserve history (Task 1 persistence).
- Partial or discontinuous phases must not produce a misleading full total; missing pops must remain distinct from explicit none (Task 2 model/view).
- Changing club/file or receiving a late GET during preview/confirmation must not install stale results (Task 2 interaction).

---

### Task 1: Offline parser and private import persistence

**Files:** Create `server/training_email.py`, `tests/test_training_email.py`; modify `server/coaching.py`, `tests/test_coaching.py` (or new route-focused test file using existing fixtures).

**Interfaces:**
- Produces `parse_training_email(content: bytes, filename: str) -> dict`, raising `TrainingEmailError` with a safe French user message. Returns report fields plus declared `club_name`, optional `club_id` for route validation (these identity fields may be moved under source metadata before persistence).
- Report remains `{report_id: string|null, season, round, team, individual, observed_at, provenance, key}` with `schema_version: 2` for new reports. API period requests remain unchanged.
- Optional `ReportPlayer.energy` is a discriminated object: `{kind: 'label', before: string|null, after: string|null}` or `{kind: 'numeric', scale: 'unreported', before: number|null, after: number|null}`. Keep legacy numeric `energy_before/after` readable.
- Individual skill entries retain `{skill, sessions, pops}` and add optional `trainer: {name: string|null, level: number|null, type: string|null}|null`.
- Provenance distinguishes `source: 'Classic API'` from `source: 'Classic email'`, with mail `source_format: 'html'|'eml'`. Do not persist raw mail/HTML/headers.
- New POST `/api/clubs/{team_id}/coaching/import-preview`, multipart field `file`, returns the existing CoachingPreview shape with `kind:'report'`; use the existing `/confirm` endpoint. Preview warnings carry safe static translatable strings; disagreement counts/details belong in structured fields if needed.
- Reports for a selected period remain separately selectable by source/key. API conflict behavior stays protective; mail storage keys include normalized digest and period. New optional fields may enrich only through a distinct traceable observation or safe semantic equivalence; no mutation of old proof.

- [ ] Write parser tests first: synthetic two-phase Classic HTML gives literal IDs, periods, CSR, sessions, trainers, labels and explicit no-pops; MIME encodings produce the same semantics; missing required phase markers/IDs, duplicate rows, unsupported formats, bounds, contradictory values and ambiguous multipart reports reject.
- [ ] Run `C:\brt\.venv\Scripts\python.exe -m pytest tests/test_training_email.py -q` and record expected red evidence.
- [ ] Implement parser with bounded standard-library parsing; support actual report structure while keeping fixtures entirely synthetic.
- [ ] Write failing integration tests: no credentials/network required, wrong local club/name/ID rejected, missing historical players warn, preview no write, confirmation survives reload, duplicates unchanged, distinct source/version retained with conflict warning, wrong owner/team/revision/expiry rejects, old API null/absent semantics stable.
- [ ] Extend API phase normalization to keep trainer metadata and typed energy, and implement import-preview/confirmation integration without weakening existing API account binding.
- [ ] Run parser/routes tests and existing coaching/progression tests. Run the Python suite once before final handoff; report any failures by name.
- [ ] Self-review privacy/limits/concurrency and commit only Task 1 files. Write a report including contract deviations, tests, red evidence and remaining concerns.

### Task 2: Report summaries and import UI

**Files:** Modify `web/src/coaching-model.ts`, `web/src/coaching.tsx`, relevant coaching CSS, `web/src/i18n.ts` (or actual locale files); add/modify `web/tests/coaching-*.test.*`.

**Interfaces:**
- Consumes Task 1's report and multipart-preview contract. Use confirmed exact contract from its report.
- Produces exported pure `trainingReportSummary(report: TrainingReport)` with per-phase CSR known/population counts, positive/negative/stable counts, sessions known/unknown, whole-level changes known/unknown, and per-player continuous total coverage plus explicit discontinuities. Summary is only for one selected report.
- Existing Classic API preview/confirm and statistic views stay usable. Local file import works with no Classic account access.
- Unknown phase/player arrays and old numeric energy fields remain readable. Source stamp, period selector options and preview clearly identify mail/API and destination.

- [ ] Write failing model tests with literal partial/continuous/discontinuous trajectories and unequal populations; assert total only on known continuous paths, no double count, null/[] differences, unknown sessions and negative CSR retained.
- [ ] Implement typed report extensions and summary calculation.
- [ ] Write failing view/interaction tests for file selection, multipart preview then confirm/cancel, trainer levels, text energy, coverage warnings, errors and stale club/file/GET behavior.
- [ ] Implement file import alongside API path, readable phase/total cards and details; preserve existing request race guards and unsaved-changes protection.
- [ ] Add all new strings in existing French/English/Spanish/Italian dictionaries; provide responsive layout using existing components.
- [ ] Run all Node tests plus `npm run build` in `web`; self-review and commit only Task 2 files. Report red/green evidence and remaining concerns.

### Task 3: Help, integrated verification and final review

**Files:** Modify existing help content and `docs/community-coaching-methodology.md`; update README release description if repository convention warrants it; no account facts.

**Interfaces:** Consumes both implemented contracts. Produces user help explaining supported files, preview/confirm, source identity, unknown values, coverage and causal limits.

- [ ] Update help in four existing languages and methodology with actual validation scope; do not claim API live success based on mail success.
- [ ] Validate the real report privately against independently known phase/pop/session/CSR totals; retain only generic outcome in public docs.
- [ ] Run full Python and Node suites and production build on final code; run `git diff --check` and scan changed tracked files for accidental private facts.
- [ ] Exercise the local upload/preview/confirm/reload/cancel and narrow layout in browser if available, using synthetic fixture and private local test store. Record exact limitation if unavailable.
- [ ] Obtain fresh task and whole-branch review, resolve important findings with regression tests, and report final local delivery with no deployment claim.

## Execution ruling

The user approved the complete implementation and local validation after reading the design. Continue in this session with sequential implementers and fresh reviews; do not request a second approval for routine execution-method choices.

