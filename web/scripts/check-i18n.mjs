import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const folder=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../src/i18n/locales');
const source=JSON.parse(fs.readFileSync(path.join(folder,'fr.json'),'utf8'));
const selected=process.argv.slice(2).filter(arg=>['en','es','it'].includes(arg));
const report=[];
const parameters=value=>[...value.matchAll(/\{([A-Za-z][A-Za-z0-9_]*)\}/g)].map(match=>match[1]).sort().join('|');
const edges=value=>[value.match(/^\s*/)[0],value.match(/\s*$/)[0]].join('|');
for(const locale of selected.length?selected:['en','es','it']){
  const file=path.join(folder,locale+'.json');
  const catalog=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):{};
  const missing=Object.keys(source).filter(key=>!Object.hasOwn(catalog,key));
  const extra=Object.keys(catalog).filter(key=>!Object.hasOwn(source,key));
  const invalid=[];
  for(const [key,value] of Object.entries(catalog)){
    if(typeof value!=='string')invalid.push({key,reason:'not-a-string'});
    else if(parameters(key)!==parameters(value))invalid.push({key,reason:'parameters'});
    else if(edges(key)!==edges(value))invalid.push({key,reason:'edge-spacing'});
    else if(/\uFFFD|[\uD800-\uDFFF]/u.test(value))invalid.push({key,reason:'invalid-unicode'});
  }
  report.push({locale,keys:Object.keys(catalog).length,missing:missing.length,extra:extra.length,invalid:invalid.length,examples:[...missing.slice(0,5).map(key=>({key,reason:'missing'})),...extra.slice(0,5).map(key=>({key,reason:'extra'})),...invalid.slice(0,10)]});
}
console.log(JSON.stringify({sourceKeys:Object.keys(source).length,report},null,2));
if(report.some(item=>item.missing||item.extra||item.invalid))process.exitCode=1;
