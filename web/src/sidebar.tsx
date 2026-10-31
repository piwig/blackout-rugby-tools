import {useEffect,useState} from 'react';
import {LayoutDashboard,Sprout,Users,CalendarRange,BarChart3,Building2,Plug,BookOpen,LogOut,X,Sparkles,TrendingUp,UserRound,MessageCircle,ChevronDown,Dumbbell,Palmtree,ArrowUpRight} from 'lucide-react';
import {tr} from './i18n';
import {ProfileAvatar,type ProfilePreferences} from './profile';
import {visibleNavigationGroups,readNavigationExpansion,revealNavigationGroup,saveNavigationExpansion,type NavigationId,type NavigationGroupId} from './navigation';

const icons={home:LayoutDashboard,squad:Users,optimization:Sparkles,matches:BarChart3,season:CalendarRange,academy:Sprout,training:Dumbbell,progression:TrendingUp,stadium:Building2,vacation:Palmtree,profile:UserRound,settings:Plug,contact:MessageCircle,guide:BookOpen};

// Literal keys keep every navigation label available to the translation extractor.
export function navigationLabels():Record<NavigationId,string>{
  return {home:tr('Tableau de bord'),squad:tr('Effectif & XV'),optimization:tr('Optimisation'),matches:tr('Analyse des matchs'),season:tr('Saison & calendrier'),academy:tr('Académie'),training:tr('Entraînement'),progression:tr('Progression'),stadium:tr('Stade & finances'),vacation:tr('Mode vacances'),profile:tr('Profil & affichage'),settings:tr('Connexion & données'),contact:tr('Contact & idées'),guide:tr('Tutoriel & aide')};
}

type SidebarProps={
  page:string;selection:boolean;username:string;profile:ProfilePreferences;displayName:string;
  busy:boolean;mobile:boolean;open:boolean;onClose:()=>void;go:(page:string)=>void;onLogout:()=>void;
};

export function Sidebar({page,selection,username,profile,displayName,busy,mobile,open,onClose,go,onLogout}:SidebarProps){
  const storageKey='brt-navigation:'+encodeURIComponent(username);
  const storage=()=>{try{return window.localStorage}catch{return undefined}};
  const [expanded,setExpanded]=useState(()=>readNavigationExpansion(storage(),storageKey,page));
  useEffect(()=>{setExpanded(current=>revealNavigationGroup(current,page))},[page]);
  useEffect(()=>{saveNavigationExpansion(storage(),storageKey,expanded)},[expanded,storageKey]);
  const labels=navigationLabels();
  const groupLabels:Record<NavigationGroupId,string>={match:tr('Préparer le match'),development:tr('Faire progresser'),club:tr('Piloter le club'),account:tr('Mon espace')};
  const route=(id:NavigationId)=>{
    const Icon=icons[id];
    return <button key={id} type="button" aria-current={page===id?'page':undefined} className={'sidebar-route'+(page===id?' active':'')} onClick={()=>{if(page===id)onClose();else go(id)}}><Icon size={18} aria-hidden="true"/><span>{labels[id]}</span>{page===id&&<span className="nav-dot" aria-hidden="true"/>}</button>;
  };
  return <aside className={'sidebar grouped-sidebar'+(open?' is-open':'')} inert={mobile&&!open} role={mobile&&open?'dialog':undefined} aria-modal={mobile&&open?true:undefined} aria-label={mobile&&open?tr('Menu de navigation'):undefined}>
    <div className="sidebar-masthead">
      <button type="button" className="icon-button sidebar-close" aria-label={tr('Fermer la navigation')} onClick={onClose}><X size={20}/></button>
      <a className="brand" href="#" onClick={e=>{e.preventDefault();if(page==='home')onClose();else go('home')}}><img src="/images/brt-logo-192.png" alt=""/><span>{tr('BLACKOUT')}<small>{tr('RUGBY TOOLS')}</small></span></a>
      <div className="edition"><i aria-hidden="true"/>{tr(' CLASSIC EDITION ')}<span>2.8.1</span></div>
    </div>
    <nav id="main-navigation" className="sidebar-navigation" aria-label={tr('Navigation principale')}>
      <div className="sidebar-home">{route('home')}</div>
      {visibleNavigationGroups(selection).map(group=>{
        const active=group.items.some(id=>id===page),panel='navigation-group-'+group.id;
        return <section key={group.id} className={'sidebar-group'+(active?' has-current':'')} aria-labelledby={panel+'-label'}>
          <button id={panel+'-label'} type="button" className="sidebar-group-toggle" aria-expanded={expanded[group.id]} aria-controls={panel} onClick={()=>setExpanded(current=>({...current,[group.id]:!current[group.id]}))}><span>{groupLabels[group.id]}</span><ChevronDown size={15} aria-hidden="true"/></button>
          <div id={panel} className="sidebar-group-items" hidden={!expanded[group.id]}>{group.items.map(route)}</div>
        </section>;
      })}
    </nav>
    <div className="sidebar-bottom"><div className="club-mini"><button type="button" className="profile-nav" onClick={()=>{if(page==='profile')onClose();else go('profile')}} aria-label={tr('Ouvrir mon profil')}><ProfileAvatar profile={profile} username={username} small/><span className="profile-nav-copy"><strong>{displayName}</strong><small>{tr('Mon espace privé')}</small></span><ArrowUpRight className="profile-nav-arrow" size={15} aria-hidden="true"/></button><button type="button" className="icon-button sidebar-logout" aria-label={tr('Se déconnecter')} disabled={busy} onClick={onLogout}><LogOut size={18}/></button></div></div>
  </aside>;
}
