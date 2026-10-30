const normalize = (value:string) => value.normalize('NFD').replace(/\p{M}/gu,'').toLocaleLowerCase('fr-FR').trim().replace(/\s+/g,' ');
const numeric = (value:unknown) => (typeof value==='number'||typeof value==='string'&&value.trim()!=='')&&Number.isFinite(Number(value)) ? Number(value) : null;
export function comparePlayerValues(a:unknown,b:unknown,descending:boolean,text=false):number {
  if(text){const result=normalize(String(a??'')).localeCompare(normalize(String(b??'')),'fr');return descending?-result:result}
  const first=numeric(a),second=numeric(b);
  if(first===null)return second===null?0:1;
  if(second===null)return -1;
  return descending?second-first:first-second;
}
export function matchesPlayerSearch(player:{name:string;id:string},query:string):boolean {
  const search=normalize(query);
  return normalize(player.name).includes(search)||player.id.includes(search);
}
