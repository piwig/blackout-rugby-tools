import test from 'node:test';
import assert from 'node:assert/strict';
import {basisForPage,sourceMoment} from '../src/data-basis-model.ts';

test('observed records, mixed screens and models have distinct explanations',()=>{
 assert.equal(basisForPage('squad')?.kind,'facts');
 assert.equal(basisForPage('academy')?.kind,'mixed');
 assert.equal(basisForPage('optimization')?.kind,'model');
 assert.equal(basisForPage('coaching')?.kind,'model');
 assert.equal(basisForPage('performance')?.sources,'none');
 assert.equal(basisForPage('matchday'),null);
 assert.equal(basisForPage('settings'),null);
});
test('only an observed timestamp with a timezone becomes a precise date',()=>{
 assert.equal(sourceMoment('2026-11-02 12:00:00','fr-FR'),null);
 assert.equal(sourceMoment('invalid','fr-FR'),null);
 assert.equal(sourceMoment(null,'fr-FR'),null);
 assert.match(sourceMoment('2020-01-02T12:00:00Z','fr-FR')??'',/2020/);
});
