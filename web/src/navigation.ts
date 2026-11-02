export const navigationItems = [
  {id:'home',label:'Tableau de bord'},
  {id:'squad',label:'Effectif & XV'},
  {id:'matchday',label:'Jour de match'},
  {id:'pool',label:'Vivier de joueurs'},
  {id:'performance',label:'Performances par poste'},
  {id:'coaching',label:'Staff & tactique'},
  {id:'optimization',label:'Optimisation'},
  {id:'matches',label:'Analyse des matchs'},
  {id:'season',label:'Saison & calendrier'},
  {id:'academy',label:'Académie',clubOnly:true},
  {id:'training',label:'Entraînement',clubOnly:true},
  {id:'progression',label:'Progression'},
  {id:'stadium',label:'Stade & finances',clubOnly:true},
  {id:'market',label:'Mercato & budget',clubOnly:true},
  {id:'vacation',label:'Mode vacances',clubOnly:true},
  {id:'profile',label:'Profil & affichage'},
  {id:'settings',label:'Connexion & données'},
  {id:'contact',label:'Contact & idées'},
  {id:'guide',label:'Tutoriel & aide'},
] as const;

export type NavigationId = typeof navigationItems[number]['id'];
export const navigationGroups = [
  {id:'match',label:'Préparer le match',items:['squad','matchday','coaching','performance','optimization','matches','season']},
  {id:'development',label:'Faire progresser',items:['academy','training','progression','pool']},
  {id:'club',label:'Piloter le club',items:['stadium','market','vacation']},
  {id:'account',label:'Mon espace',items:['profile','settings','contact','guide']},
] as const;
export type NavigationGroupId = typeof navigationGroups[number]['id'];
export type NavigationExpansion = Record<NavigationGroupId,boolean>;
type PreferenceStorage = Pick<Storage,'getItem'|'setItem'>;

export function isClubOnly(page:string){
  return navigationItems.some(item=>item.id===page&&'clubOnly' in item&&item.clubOnly);
}

export function visibleNavigationGroups(selection:boolean){
  return navigationGroups.map(group=>({...group,items:group.items.filter(id=>!selection||!isClubOnly(id))}))
    .filter(group=>group.items.length>0);
}

export function revealNavigationGroup(expanded:NavigationExpansion,page:string):NavigationExpansion{
  const group=navigationGroups.find(group=>group.items.some(id=>id===page));
  return group&&!expanded[group.id]?{...expanded,[group.id]:true}:expanded;
}

// Only disclosure preferences are persisted; malformed or unavailable storage never blocks navigation.
export function readNavigationExpansion(storage:PreferenceStorage|undefined,key:string,page:string):NavigationExpansion{
  const expanded:NavigationExpansion={match:true,development:true,club:true,account:false};
  try{
    const stored=JSON.parse(storage?.getItem(key)??'null');
    if(stored&&typeof stored==='object'&&!Array.isArray(stored)){
      for(const group of navigationGroups)if(typeof stored[group.id]==='boolean')expanded[group.id]=stored[group.id];
    }
  }catch{/* A private browser can deny storage, or an older preference may be invalid. */}
  return revealNavigationGroup(expanded,page);
}

export function saveNavigationExpansion(storage:PreferenceStorage|undefined,key:string,expanded:NavigationExpansion){
  try{storage?.setItem(key,JSON.stringify(Object.fromEntries(navigationGroups.map(group=>[group.id,expanded[group.id]]))))}catch{/* Navigation remains usable without persistence. */}
}
