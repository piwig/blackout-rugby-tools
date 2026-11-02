type Basis={kind:'facts'|'mixed'|'model';sources:'squad'|'academy'|'both'|'none'};
export function basisForPage(page:string):Basis|null{
 if(page==='squad')return {kind:'facts',sources:'squad'};
 if(page==='academy')return {kind:'mixed',sources:'academy'};
 if(['performance','pool','progression'].includes(page))return {kind:'facts',sources:'none'};
 if(['optimization','coaching','vacation'].includes(page))return {kind:'model',sources:'both'};
 if(['training','stadium','market'].includes(page))return {kind:'mixed',sources:page==='training'?'both':'none'};
 return null;
}
export function sourceMoment(value:unknown,locale:string):string|null{
 if(typeof value!=='string'||!/(Z|[+-]\d{2}:\d{2})$/i.test(value)||!Number.isFinite(Date.parse(value)))return null;
 return new Date(value).toLocaleString(locale,{dateStyle:'medium',timeStyle:'short'});
}
