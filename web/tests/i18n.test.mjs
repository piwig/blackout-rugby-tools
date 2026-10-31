import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

test('translation interpolates data without translating names or notes', async () => {
  const module = new URL('../src/i18n/core.ts', import.meta.url);
  assert.ok(fs.existsSync(module), 'The explicit translation core is required');
  const {translate} = await import(module);
  const catalog={'Annuler':'Cancel','Pilier':'Prop','Joueur : {name}. Note : {note}':'Player: {name}. Note: {note}'};
  assert.equal(translate(catalog,'Annuler'), 'Cancel');
  assert.equal(translate(catalog,'Joueur : {name}. Note : {note}',{name:'Annuler',note:'Pilier'}),'Player: Annuler. Note: Pilier');
  assert.equal(translate(catalog,'Unknown source'), 'Unknown source');
});

test('unsupported or missing saved languages retain the French default', async () => {
  const module = new URL('../src/i18n/core.ts', import.meta.url);
  assert.ok(fs.existsSync(module), 'The locale validator is required');
  const {normalizeLocale,languageTags} = await import(module);
  for(const value of [undefined,null,'de','EN','en-GB',{},''])assert.equal(normalizeLocale(value),'fr');
  for(const value of ['fr','en','es','it'])assert.equal(normalizeLocale(value),value);
  assert.equal(languageTags.en,'en-GB');
});

test('locale changes notify existing consumers and persist without replacing their state', async () => {
  const {getLocale,setLocale,subscribeLocale}=await import('../src/i18n/runtime.ts');
  const original=globalThis.localStorage;
  const writes=[];
  globalThis.localStorage={setItem:(key,value)=>writes.push([key,value])};
  let updates=0;
  const unsubscribe=subscribeLocale(()=>{updates++;});
  try{
    setLocale('en');
    assert.equal(getLocale(),'en');
    assert.equal(updates,1);
    assert.deepEqual(writes.at(-1),['brt-language','en']);
    setLocale('en');
    assert.equal(updates,1);
    setLocale('it');
    assert.equal(updates,2);
    unsubscribe();
    setLocale('fr');
    assert.equal(updates,2);
  }finally{unsubscribe();setLocale('fr');globalThis.localStorage=original;}
});
