import test from 'node:test';
import assert from 'node:assert/strict';
import {formatStatistic} from '../src/statistic-format.ts';
import {installCatalogs,setLocale} from '../src/i18n/runtime.ts';

installCatalogs({fr:{},en:{},es:{},it:{}});

test('small observed changes remain visible instead of becoming a displayed zero',()=>{
  setLocale('en');
  assert.equal(formatStatistic(0.04),'0.04');
  assert.equal(formatStatistic(-0.004),'-0.004');
  assert.equal(formatStatistic(0.0001),'0.0001');
  assert.equal(formatStatistic(33.33),'33.33');
});

test('statistical formatting keeps known zero, excludes invalid numbers and uses the chosen locale',()=>{
  setLocale('fr');
  assert.equal(formatStatistic(0),'0');
  assert.equal(formatStatistic(-0),'0');
  assert.equal(formatStatistic(77.78),'77,78');
  for(const value of [null,undefined,NaN,Infinity,-Infinity])assert.equal(formatStatistic(value),'—');
  assert.equal(formatStatistic('Unknown'),'Unknown');
});
