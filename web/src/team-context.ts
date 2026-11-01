import {tr} from './i18n';
import type {State,TeamKind,TeamSummary} from './types';

type TeamContext=Pick<TeamSummary,'id'|'kind'>;
export function teamKind(team:TeamContext):TeamKind {
  return team.kind??(team.id.startsWith('u20:')?'u20':team.id.startsWith('nt:')?'nt':'club');
}
export function isSelectionTeam(team:TeamContext):boolean {return teamKind(team)!=='club';}
export function isActiveSelection(d:Pick<State,'classic_account'>,team:TeamContext):boolean {
  return isSelectionTeam(team)&&!!d.classic_account?.selection_ids?.includes(team.id);
}
export function teamContextLabel(d:Pick<State,'classic_account'>,team:TeamContext):string {
  const kind=teamKind(team);
  return kind==='u20'?tr('Sélection U20'):kind==='nt'?tr('Sélection nationale'):d.classic_account?.team_ids.includes(team.id)?tr('Club du compte Classic'):tr('Club suivi');
}
export function groupedTeams(d:Pick<State,'teams'|'classic_account'>):{label:string;teams:TeamSummary[]}[] {
  const groups=[{label:tr('Clubs du compte Classic'),teams:[] as TeamSummary[]},{label:tr('Clubs suivis'),teams:[] as TeamSummary[]},{label:tr('Sélections actives'),teams:[] as TeamSummary[]},{label:tr('Sélections suspendues'),teams:[] as TeamSummary[]}];
  const seen=new Set<string>();
  for(const team of d.teams){
    if(seen.has(team.id))continue;
    seen.add(team.id);
    const index=isSelectionTeam(team)?isActiveSelection(d,team)?2:3:d.classic_account?.team_ids.includes(team.id)?0:1;
    groups[index].teams.push(team);
  }
  return groups.filter(group=>group.teams.length>0);
}
