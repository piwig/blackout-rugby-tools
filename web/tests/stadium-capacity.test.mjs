import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const compiled = ts.transpileModule(readFileSync(new URL('../src/insights.tsx', import.meta.url), 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX},
}).outputText;
const artifact = {exports: {}};
const load = id => id === './App' || id === './types' || id === './navigation-guard' || id.endsWith('.css') ? {} : require(id);
vm.runInNewContext(compiled, {module: artifact, exports: artifact.exports, require: load, structuredClone});
const api = artifact.exports;
const plain = value => JSON.parse(JSON.stringify(value));

test('zero is a deliberate empty stadium and one seat goes to the largest remainder', () => {
  assert.equal(typeof api.stadiumCapacityTarget, 'function');
  assert.deepEqual(plain(api.stadiumCapacityTarget('0')), {
    target:{standing:0, uncovered:0, covered:0, members:0, corporate:0}, error:'',
  });
  assert.deepEqual(plain(api.stadiumCapacityTarget('1').target), {
    standing:0, uncovered:1, covered:0, members:0, corporate:0,
  });
});

test('whole seats conserve the entered total, with stable category order for tied remainders', () => {
  assert.equal(typeof api.stadiumCapacityTarget, 'function');
  const cases = [
    ['7', {standing:1, uncovered:3, covered:2, members:1, corporate:0}],
    ['50', {standing:11, uncovered:20, covered:15, members:4, corporate:0}],
    ['1179', {standing:259, uncovered:460, covered:354, members:94, corporate:12}],
    ['10000', {standing:2200, uncovered:3900, covered:3000, members:800, corporate:100}],
  ];
  for (const [total, target] of cases) assert.deepEqual(plain(api.stadiumCapacityTarget(total)), {target, error:''});
  for (let total = 0; total <= 500; total++) {
    const {target,error} = api.stadiumCapacityTarget(String(total));
    assert.equal(error, '');
    assert.equal(Object.values(target).reduce((sum, value) => sum + value, 0), total);
    assert.ok(Object.values(target).every(value => Number.isInteger(value) && value >= 0));
  }
});

test('the largest supported total keeps every category within the backend capacity limit', () => {
  assert.equal(typeof api.stadiumCapacityTarget, 'function');
  assert.deepEqual(plain(api.stadiumCapacityTarget('2564103')), {
    target:{standing:564103, uncovered:1000000, covered:769231, members:205128, corporate:25641}, error:'',
  });
  for (const value of ['2564104', '5000000', '9007199254740992']) {
    const result = api.stadiumCapacityTarget(value);
    assert.equal(result.target, null);
    assert.ok(result.error);
  }
});

test('missing or invalid totals never become a real zero-capacity target', () => {
  assert.equal(typeof api.stadiumCapacityTarget, 'function');
  for (const value of ['', '   ', '-1', '1.5', '1,5', '1e3', 'NaN', 'Infinity', 'abc']) {
    const result = api.stadiumCapacityTarget(value);
    assert.equal(result.target, null, value);
    assert.ok(result.error, value);
  }
});
