/** Conservative, one-time display-text codemod. Never translates data expressions. */
import ts from 'typescript';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const displayAttributes = new Set(['title', 'placeholder', 'aria-label', 'alt', 'aria-description']);
const literalTags = new Set(['code', 'pre', 'script', 'style']);
const entities = {amp:'&', lt:'<', gt:'>', quot:'"', apos:"'", nbsp:'\u00a0'};
const decode = text => text.replace(/&(#x[\da-f]+|#\d+|amp|lt|gt|quot|apos|nbsp);/gi, (all, key) => key[0] === '#' ? String.fromCodePoint(parseInt(key.slice(key[1].toLowerCase()==='x'?2:1), key[1].toLowerCase()==='x'?16:10)) : entities[key.toLowerCase()] ?? all);
function jsxText(text) {
  const lines = text.split(/\r\n|\n|\r/);
  let last = 0;
  lines.forEach((line, i) => {if (/[^ \t]/.test(line)) last=i;});
  return decode(lines.map((line, i) => {
    let value=line.replace(/\t/g,' ');
    if(i!==0)value=value.replace(/^ +/,'');
    if(i!==lines.length-1)value=value.replace(/ +$/,'');
    return value ? value+(i!==last?' ':'') : '';
  }).join(''));
}
function inLiteralTag(node) {
  for(let parent=node.parent;parent;parent=parent.parent){
    if(ts.isJsxElement(parent)&&literalTags.has(parent.openingElement.tagName.getText()))return true;
  }
  return false;
}
export function transformSource(source, filename) {
  const tree=ts.createSourceFile(filename,source,ts.ScriptTarget.Latest,true,filename.endsWith('.tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS);
  const edits=[],segments=[],references=[],candidates=[];
  function add(node, text, kind, start=node.getStart(tree), end=node.end) {
    if(!/[\p{L}]/u.test(text))return;
    const line=tree.getLineAndCharacterOfPosition(node.getStart(tree)).line+1;
    segments.push({source:text,file:filename,line,kind});
    edits.push({start,end,text:'{tr('+JSON.stringify(text)+')}'});
  }
  function visit(node) {
    if(ts.isJsxText(node)&&!inLiteralTag(node))add(node,jsxText(node.text),'jsx-text',node.pos);
    if(ts.isJsxAttribute(node)&&displayAttributes.has(node.name.text)&&node.initializer&&ts.isStringLiteral(node.initializer)&&!inLiteralTag(node))add(node.initializer,decode(node.initializer.text),'attribute:'+node.name.text);
    if(ts.isCallExpression(node)&&node.expression.getText(tree)==='tr'&&node.arguments[0]&&ts.isStringLiteral(node.arguments[0]))references.push({source:node.arguments[0].text,file:filename,line:tree.getLineAndCharacterOfPosition(node.pos).line+1,kind:'explicit-tr'});
    if(ts.isStringLiteral(node)&&!ts.isJsxAttribute(node.parent)&&!ts.isImportDeclaration(node.parent)&&/[àâçéèêëîïôùûüœ]|[A-Za-z]{2} [A-Za-zÀ-ÿ]{2}/.test(node.text)&&!/^https?:|^\{|^\/|^\[/.test(node.text))candidates.push({source:node.text,file:filename,line:tree.getLineAndCharacterOfPosition(node.pos).line+1,kind:ts.SyntaxKind[node.parent.kind]});
    ts.forEachChild(node,visit);
  }
  visit(tree);
  let code=source;
  for(const edit of edits.sort((a,b)=>b.start-a.start))code=code.slice(0,edit.start)+edit.text+code.slice(edit.end);
  if(edits.length&&!tree.statements.some(statement=>ts.isImportDeclaration(statement)&&statement.moduleSpecifier.text==='./i18n'))code="import {tr} from './i18n';\n"+code;
  return {code,segments,references,candidates};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const web=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
  const folder=path.join(web,'src','i18n');fs.mkdirSync(path.join(folder,'locales'),{recursive:true});
  const apply=process.argv.includes('--apply');
  const targets=process.argv.filter(arg=>arg.startsWith('--file=')).map(arg=>arg.slice(7));
  const excluded=new Set(process.argv.filter(arg=>arg.startsWith('--exclude=')).map(arg=>arg.slice(10)));
  const catalogPath=path.join(folder,'locales','fr.json');
  const catalog=fs.existsSync(catalogPath)?JSON.parse(fs.readFileSync(catalogPath,'utf8')):{};
  const manifest=[],candidates=[];let changed=0;
  for(const file of fs.readdirSync(path.join(web,'src')).filter(file=>/\.tsx?$/.test(file))){
    const filename=path.join(web,'src',file),source=fs.readFileSync(filename,'utf8');
    const result=transformSource(source,'web/src/'+file);
    for(const entry of [...result.segments,...result.references]){catalog[entry.source]=entry.source;manifest.push(entry);}
    candidates.push(...result.candidates);
    if(apply&&!excluded.has(file)&&(!targets.length||targets.includes(file))&&result.code!==source){fs.writeFileSync(filename,result.code);changed++;}
  }
  fs.writeFileSync(catalogPath,JSON.stringify(Object.fromEntries(Object.entries(catalog).sort(([a],[b])=>a.localeCompare(b,'fr'))),null,2)+'\n');
  fs.writeFileSync(path.join(folder,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
  fs.writeFileSync(path.join(folder,'candidates.json'),JSON.stringify(candidates,null,2)+'\n');
  console.log(JSON.stringify({catalog:'web/src/i18n/locales/fr.json',keys:Object.keys(catalog).length,occurrences:manifest.length,dynamicCandidates:candidates.length,changedFiles:changed}));
}
