import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import ts from 'typescript';
import vm from 'node:vm';
import {createRequire} from 'node:module';

const require=createRequire(import.meta.url);

test('explicit extraction preserves manager data, business values and JSX whitespace', async () => {
  const module = new URL('../scripts/i18n-extract.mjs', import.meta.url);
  assert.ok(fs.existsSync(module), 'The explicit display-text extractor is required');
  const {transformSource} = await import(module);
  const input = `const role='Pilier'; const note='Annuler'; function View({player}) {return <section><button title="Fermer">Annuler</button><p>{player.name}</p><blockquote>{note}</blockquote><option value="Pilier">Pilier</option><code>team_id</code><p>Club : {player.name} · prêt</p></section>}`;
  const result = transformSource(input, 'View.tsx');
  assert.match(result.code, /title=\{tr\("Fermer"\)\}/);
  assert.match(result.code, />\{tr\("Annuler"\)\}</);
  assert.match(result.code, /<p>\{player.name\}<\/p>/);
  assert.match(result.code, /<blockquote>\{note\}<\/blockquote>/);
  assert.match(result.code, /value="Pilier"/);
  assert.match(result.code, /const role='Pilier'/);
  assert.match(result.code, /<code>team_id<\/code>/);
  assert.match(result.code, /tr\("Club : "\)/);
  assert.match(result.code, /tr\(" · prêt"\)/);
  assert.deepEqual(transformSource(result.code, 'View.tsx').segments, []);
});

test('French rendering preserves JSX entities and multiline whitespace exactly', async () => {
  const {transformSource}=await import('../scripts/i18n-extract.mjs');
  const source=`export function View(){return <section title="Rugby &amp; équipe"><p> Première ligne\n  deuxième ligne <strong>repère</strong> suite.</p><p>Club &amp; joueur &#233; &amp;amp;</p></section>}`;
  function render(code){
    const artifact={exports:{}};
    const compiled=ts.transpileModule(code,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
    vm.runInNewContext(compiled,{module:artifact,exports:artifact.exports,require:id=>id==='./i18n'?{tr:source=>source}:require(id)});
    return require('react-dom/server').renderToStaticMarkup(require('react').createElement(artifact.exports.View));
  }
  assert.equal(render(transformSource(source,'View.tsx').code),render(source));
});
