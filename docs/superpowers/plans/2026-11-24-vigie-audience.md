# BRT Audience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Connect BRT screen views to the existing Umami/Vigie installation.

**Architecture:** An opt-in server environment exposes public tracker settings;
the React app emits only fixed, sanitized screen views. A dedicated Umami team
and reader isolate BRT; Vigie exposes existing 7/30-day aggregate routes.

**Tech Stack:** Existing FastAPI/Python, React/TypeScript, Umami 3.3.1 and Vigie.

**Spec:** `docs/superpowers/specs/2026-11-24-vigie-audience-design.md`, approved
with implementation and publication on 24 November 2026.

## Global Constraints

- No dependency or paid service, no Classic writes, no changes to other projects.
- No personal/sporting data, real URL/query/hash, user properties or raw titles.
- Measurement optional; disabled by default and fail closed on invalid config.
- Four languages; respect DNT, local opt-out and authenticated admin exclusion.
- Operational proofs/secrets remain private and excluded from Git.
- User authorized implementation and publication; do not ask again for ordinary
  technical choices. Root coordinates independent frontend/backend work.

## Review Focus

- Late options/script response after opt-out, admin login or changed screen must
  not emit stale views: test these transitions in task 2.
- Malformed/referrer URLs and unknown screen IDs must not leak user input: task 2.
- Failed/denied storage and failed collector must leave app functional: task 2.
- Invalid environment must not broaden CSP or expose secrets: task 1.
- BRT reader must not access/write any other site: operational checks task 3.

### Task 1: Server configuration and CSP

**Files:** `server/audience.py`, `server/main.py`, `tests/test_audience.py`,
`docs/deployment.md`, `README.md`.

**Interfaces:** Public `GET /api/audience/options` returns `{enabled:false}` when
disabled, otherwise `{enabled:true,script_url:string,website_id:string,hostname:string}`.
Configure `BRT_AUDIENCE_ENABLED`, `BRT_AUDIENCE_SCRIPT_URL`,
`BRT_AUDIENCE_WEBSITE_ID`, `BRT_AUDIENCE_HOSTNAME`; validate HTTPS script URL,
UUID and hostname, reject credentials/query/hash. Allow only collector origin in
script-src/connect-src. Never expose credentials.

- [x] Write and run failing endpoint/CSP tests for default disabled, enabled
  sanitized config and malformed environment. Verify unknown APIs remain private.
- [x] Implement `audience_options()` and origin calculation as pure helpers;
  integrate read-only public endpoint and precise CSP addition.
- [x] Run `C:\brt\.venv\Scripts\python.exe -m pytest tests/test_audience.py -q`.
- [x] Document configuration and privacy semantics, then commit this unit.

### Task 2: Optional sanitized screen measurement

**Files:** `web/src/audience.ts`, `web/src/audience-ui.tsx`,
`web/src/App.tsx`, locale catalogs and `web/tests/audience*.test.*`.

**Interfaces:** Consume task 1 options directly. Emit manually constructed Umami
objects with only website, hostname, synthetic url, fixed title, sanitized
referrer. Use data-auto-track=false and credentials omitted. Track settled public,
registration, onboarding and known navigation screens, never initial boot/error.
Opt-out lives locally, no account identifier in key or payload.

- [x] Write tests and observe RED for strict payloads, view A/B/A and consecutive
  duplicates, admin/DNT/opt-out suppression, late script/options and storage/network
  failures. Use existing Node rendering/test patterns.
- [x] Implement module, lifecycle and compact accessible information/choice on
  login and in app. Translate visible copy into FR/EN/ES/IT.
- [x] Run targeted Node tests, all Node tests, catalog check and build; report
  evidence to coordinator, without touching server/deployment files.
- [x] Review integration and commit this unit.

### Task 3: Publish and verify receipt

**Files:** deployment docs and private operational receipts only; existing Vigie
production config append and private environment, no unrelated project edits.

- [x] Review whole diff independently; resolve important findings with tests.
- [x] Run full Python/Node suites, catalog check and production build.
- [x] Inspect existing Umami setup. Reuse suitable BRT site/reader if present;
  otherwise create dedicated team/site/view-only reader using authorized admin
  access. Never reset an existing credential to obtain access.
- [ ] Back up before mutation. Configure BRT reader privately, append Vigie
  audience-only project, sync and restart; verify BRT readable, other site denied
  and writes denied with that reader. Preserve all existing projects.
- [ ] Package committed BRT source/build, back up and publish with rollback;
  preserve auth/CAPTCHA/private APIs and current app/game settings.
- [ ] In Chrome verify actual screen and privacy choice; inspect sanitized request
  and prove receipt in Umami/Vigie. Separate recipe traffic from organic traffic.
- [ ] Test dashboard/JSON/MCP availability separately and record exact limitations.
- [ ] Save private operational proof and update public docs with sanitized outcome.

## Self-review

Spec requirements map to tasks 1–3. Tasks 1/2 share only the public options shape;
root owns server/deployment, frontend implementer owns web files. Community research
continues independently, with no publication into a channel that forbids it.
