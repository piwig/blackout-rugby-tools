import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import ts from 'typescript';
import vm from 'node:vm';

const compiled = ts.transpileModule(readFileSync(new URL('../src/insights.tsx', import.meta.url), 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX},
}).outputText;
const artifact = {exports: {}};
const {createRequire} = await import('node:module');
const require = createRequire(import.meta.url);
const load = id => id === './App' || id === './types' || id === './navigation-guard' || id.endsWith('.css') ? {} : require(id);
vm.runInNewContext(compiled, {module: artifact, exports: artifact.exports, require: load, structuredClone});
const api = artifact.exports;

test('planned session prefills only its real reference and skill, leaving actual date and note empty', () => {
  assert.equal(typeof api.plannedSessionDraft, 'function');
  const draft = api.plannedSessionDraft({season: 63, week: 14, slot: 3, skill: 'handling', declared: true});
  assert.deepEqual(JSON.parse(JSON.stringify(draft)), {
    season: '63', week: '14', slot: '3', skill: 'handling', performed: '', note: '',
  });
});

test('empty or invalid performed date cannot produce a declaration timestamp or throw', () => {
  assert.equal(typeof api.validateSessionDate, 'function');
  for (const value of ['', '   ', 'not-a-date', '2026-13-01T18:30']) {
    const result = api.validateSessionDate(value);
    assert.equal(result.performedAt, null);
    assert.ok(result.error);
  }
});

test('a valid performed date preserves the supplied observation instant', () => {
  assert.equal(typeof api.validateSessionDate, 'function');
  const result = api.validateSessionDate('2026-10-15T18:30+02:00', Date.parse('2026-10-16T00:00Z'));
  assert.equal(result.performedAt, '2026-10-15T16:30:00.000Z');
  assert.equal(result.error, '');
});

test('a future performed date is refused locally with an actionable date error', () => {
  assert.equal(typeof api.validateSessionDate, 'function');
  const result = api.validateSessionDate('2026-10-17T18:30+02:00', Date.parse('2026-10-16T00:00Z'));
  assert.equal(result.performedAt, null);
  assert.match(result.error, /futur/);
});

test('acknowledging an earlier declaration never marks newer form edits as saved', () => {
  assert.equal(typeof api.sessionDraftReducer, 'function');
  const draft = {season:'63',week:'14',slot:'3',skill:'handling',performed:'2026-10-15T18:30',note:'Vérifié'};
  let state = {draft, baseline: {...draft, note: ''}};
  state = api.sessionDraftReducer(state, {type:'edit', draft:{...draft, skill:'speed',note:'Nouvelle vérification'}});
  state = api.sessionDraftReducer(state, {type:'saved', draft});
  assert.equal(state.draft.skill, 'speed');
  assert.equal(state.draft.note, 'Nouvelle vérification');
  assert.notDeepEqual(state.draft, state.baseline);
  state = api.sessionDraftReducer(state, {type:'saved', draft:state.draft});
  assert.deepEqual(state.draft, state.baseline);
});

test('zone cells use their zone denominator and leave an unobserved zone without a percentage', () => {
  assert.equal(typeof api.zoneAttackValue, 'function');
  assert.equal(api.zoneAttackValue(1, 3), '1 · 33,3 %');
  assert.equal(api.zoneAttackValue(0, 3), '0 · 0 %');
  assert.equal(api.zoneAttackValue(0, 0), '—');
});

test('opponent matrix exposes row and column headers plus empty-zone explanation', () => {
  assert.equal(typeof api.ZoneAttackMatrix, 'function');
  const React = require('react');
  const {renderToStaticMarkup} = require('react-dom/server');
  const empty = {'Percussion':0,'Pick and go':0,'Large':0,'Créatif':0,'Jeu au pied':0};
  const html = renderToStaticMarkup(React.createElement(api.ZoneAttackMatrix, {
    matrix: {'22': {...empty, Large:1, Percussion:2},'40': empty,'40A':empty,'22A':empty},
  }));
  assert.match(html, /<caption>/);
  assert.match(html, /scope="col"[^>]*>Large/);
  assert.match(html, /scope="row"[^>]*>22</);
  assert.match(html, /1 · 33,3 %/);
  assert.match(html, /Aucune observation/);
  assert.doesNotMatch(html, /NaN|Infinity/);
});
