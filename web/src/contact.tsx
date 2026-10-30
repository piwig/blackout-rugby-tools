import {useCallback, useEffect, useId, useRef, useState} from 'react';
import {Bug, CheckCircle2, Inbox, Lightbulb, Mail, RefreshCw, Send, ShieldCheck, Sparkles} from 'lucide-react';
import {request, type Actions} from './App';
import {AntiBot} from './antibot';
import './contact.css';

type ContactKind = 'bug'|'improvement'|'feature';
type ContactStatus = 'new'|'reviewing'|'planned'|'resolved';
export type ContactTicket = {
  id:string;kind:ContactKind;subject:string;message:string;email:string;
  status:ContactStatus;revision:number;created_at:string;updated_at:string;
  author?:string|null;notification_status?:'pending'|'disabled'|'sent'|'failed';
};
const kinds = [
  {id:'bug' as const,label:'Un bug',hint:'Quelque chose ne fonctionne pas.',icon:Bug},
  {id:'improvement' as const,label:'Une amélioration',hint:'Rendre un usage plus simple.',icon:Lightbulb},
  {id:'feature' as const,label:'Une nouveauté',hint:'Proposer une nouvelle fonction.',icon:Sparkles},
];
const kindNames:Record<ContactKind,string> = {bug:'Bug',improvement:'Amélioration',feature:'Nouveauté'};
const statusNames:Record<ContactStatus,string> = {new:'Reçu',reviewing:'En cours de lecture',planned:'Prévu',resolved:'Traité'};
const notificationNames = {pending:'Notification en attente',disabled:'Notification mail désactivée',sent:'Notification mail envoyée',failed:'Notification mail non envoyée · message conservé'};
const dateLabel = (value:string) => new Date(value).toLocaleString('fr-FR',{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'});
const errorText = (error:unknown) => error instanceof Error ? error.message : 'La demande n’a pas abouti. Réessayez.';

export function ContactForm({csrf,email='',onDone}:{csrf?:string;email?:string;onDone?:(ticket:ContactTicket)=>void}) {
  const id=useId(),[kind,setKind]=useState<ContactKind>('bug'),[subject,setSubject]=useState(''),[message,setMessage]=useState('');
  const [reply,setReply]=useState(email),[website,setWebsite]=useState(''),[consent,setConsent]=useState(false);
  const [saving,setSaving]=useState(false),[error,setError]=useState(''),[sent,setSent]=useState<ContactTicket|null>(null);
  const [captchaToken,setCaptchaToken]=useState<string|null>(null),[captchaReset,setCaptchaReset]=useState(0);
  const mounted=useRef(false),emailEdited=useRef(false),scope=csrf||'public',current=useRef(scope);current.current=scope;
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[]);
  useEffect(()=>{if(!emailEdited.current)setReply(email)},[email]);
  const submit=async()=>{
    if(saving||!consent||captchaToken===null)return;
    if(!subject.trim()||!message.trim()){setError('Renseignez un sujet et un message.');return}
    if(/[\r\n]/.test(reply)){setError('Indiquez une seule adresse e-mail valide.');return}
    setSaving(true);setError('');
    try {
      const result=await request('/contact',{kind,subject,message,email:reply,website,captcha_token:captchaToken||''},csrf) as {ticket:ContactTicket};
      if(mounted.current&&current.current===scope){setSent(result.ticket);setSubject('');setMessage('');setConsent(false);onDone?.(result.ticket)}
    } catch(error) {
      if(mounted.current&&current.current===scope)setError(errorText(error));
    } finally {if(mounted.current&&current.current===scope){setSaving(false);setCaptchaToken(null);setCaptchaReset(value=>value+1)}}
  };
  if(sent)return <div className="contact-success" role="status">
    <span className="contact-success-icon"><CheckCircle2 size={30}/></span>
    <h3>Votre message est bien enregistré.</h3>
    <p>Pierig peut maintenant le retrouver dans sa boîte de réception. L’adresse de réponse indiquée est <strong>{sent.email}</strong>.</p>
    <p>{csrf?'Vous pouvez suivre son état dans votre historique ci-dessous.':'Conservez cette référence si vous souhaitez reparler de ce message.'}</p>
    <span className="contact-reference">Référence : {sent.id}</span>
    <button type="button" className="button secondary" onClick={()=>{setSent(null);setError('')}}>Écrire un autre message</button>
  </div>;
  return <form className="contact-form" onSubmit={event=>{event.preventDefault();void submit()}} aria-busy={saving}>
    <fieldset className="contact-kinds" disabled={saving}><legend>Que souhaitez-vous partager ?</legend>
      <div>{kinds.map(item=><label className={kind===item.id?'selected':''} key={item.id}>
        <input type="radio" name={id+'-kind'} value={item.id} checked={kind===item.id} onChange={()=>setKind(item.id)}/>
        <item.icon size={20} aria-hidden="true"/><strong>{item.label}</strong><small>{item.hint}</small>
      </label>)}</div>
    </fieldset>
    <label htmlFor={id+'-subject'}>Le sujet<input id={id+'-subject'} required maxLength={160} value={subject} disabled={saving} onChange={e=>setSubject(e.target.value)} placeholder="Ex. La date d’un match ne s’affiche pas"/></label>
    <label htmlFor={id+'-message'}>Votre message<textarea id={id+'-message'} required maxLength={4000} rows={6} value={message} disabled={saving} onChange={e=>setMessage(e.target.value)} aria-describedby={id+'-message-help'} placeholder={kind==='bug'?'Indiquez l’écran concerné, ce que vous avez fait et le résultat attendu.':'Décrivez votre idée et ce qu’elle vous aiderait à faire.'}/><small id={id+'-message-help'} className="contact-field-help">Sans mot de passe, clé API ni autre secret. <span>{message.length} / 4 000</span></small></label>
    <label htmlFor={id+'-email'}>Votre e-mail pour une réponse<input id={id+'-email'} type="email" required maxLength={254} autoComplete="email" inputMode="email" value={reply} disabled={saving} onChange={e=>{emailEdited.current=true;setReply(e.target.value)}} aria-describedby={id+'-email-help'}/><small id={id+'-email-help'}>Utilisé pour vous répondre au sujet de ce message.</small></label>
    <div className="contact-trap" aria-hidden="true"><label htmlFor={id+'-website'}>Site web<input id={id+'-website'} name="website" tabIndex={-1} autoComplete="off" value={website} onChange={e=>setWebsite(e.target.value)}/></label></div>
    <label className="contact-consent"><input type="checkbox" required checked={consent} disabled={saving} onChange={e=>setConsent(e.target.checked)}/><span>Je transmets ce message et mon e-mail à Pierig, administrateur de l’outil{csrf?', avec mon identifiant de connexion':''}.</span></label>
    <p className="contact-privacy"><ShieldCheck size={16} aria-hidden="true"/><span>Seuls les champs de ce formulaire{csrf?' et votre identifiant':''} sont partagés. Vos données de club ne sont pas jointes.</span></p>
    <AntiBot action="contact" onToken={setCaptchaToken} resetKey={captchaReset}/>
    {error&&<p className="notice error" role="alert">{error}</p>}
    <button className="button primary contact-submit" disabled={saving||!consent||captchaToken===null}><Send size={17}/>{saving?'Enregistrement du message…':'Envoyer à Pierig'}</button>
  </form>;
}

function useTickets(path:string, scope:string) {
  const [state,setState]=useState<{scope:string;items:ContactTicket[];loading:boolean;error:string;hasMore:boolean}>({scope,items:[],loading:true,error:'',hasMore:false});
  const current=useRef(scope),mounted=useRef(false),sequence=useRef(0);current.current=scope;
  const load=useCallback(async(offset=0)=>{
    const token=++sequence.current;
    setState(previous=>({...previous,loading:true,error:''}));
    try {
      const result=await request(path+'?offset='+offset) as {items:ContactTicket[];has_more:boolean};
      if(mounted.current&&current.current===scope&&sequence.current===token)setState(previous=>({scope,
        items:offset?[...previous.items,...result.items.filter(item=>!previous.items.some(existing=>existing.id===item.id))]:result.items,
        loading:false,error:'',hasMore:result.has_more}));
    } catch(error) {
      if(mounted.current&&current.current===scope&&sequence.current===token)setState(previous=>({...previous,loading:false,error:errorText(error)}));
    }
  },[path,scope]);
  useEffect(()=>{
    mounted.current=true;setState({scope,items:[],loading:true,error:'',hasMore:false});void load();
    return()=>{mounted.current=false;sequence.current++};
  },[scope,load]);
  return {items:state.scope===scope?state.items:[],error:state.scope===scope?state.error:'',loading:state.scope===scope?state.loading:true,hasMore:state.scope===scope&&state.hasMore,load};
}

function Ticket({ticket,children,admin=false}:{ticket:ContactTicket;children?:React.ReactNode;admin?:boolean}) {
  return <article className="contact-ticket">
    <div className="contact-ticket-heading"><span className="contact-kind">{kindNames[ticket.kind]}</span><span className={'contact-status contact-status-'+ticket.status}>{statusNames[ticket.status]}</span><time dateTime={ticket.created_at}>{dateLabel(ticket.created_at)}</time></div>
    <h3>{ticket.subject}</h3><p className="contact-message">{ticket.message}</p>
    <div className="contact-ticket-meta"><span>{admin?(ticket.author?'Manager : '+ticket.author:'Depuis la page de connexion'):'Votre adresse de réponse'}</span><span className="contact-email"><Mail size={14} aria-hidden="true"/>{ticket.email}</span></div>
    <details className="contact-ticket-details"><summary>Référence et suivi</summary><p>Référence : <span>{ticket.id}</span></p><p>Suivi mis à jour le {dateLabel(ticket.updated_at)}</p>{admin&&ticket.notification_status&&<p>{notificationNames[ticket.notification_status]}</p>}</details>
    {children}
  </article>;
}

export function ContactPage(props:Actions) {
  const scope=props.d.user.username+':'+props.d.csrf,history=useTickets('/contact',scope);
  const [email,setEmail]=useState(''),[emailError,setEmailError]=useState('');
  useEffect(()=>{
    let active=true;setEmail('');setEmailError('');
    request('/account/contact').then(result=>{if(active)setEmail(result?.email||'')}).catch(()=>{if(active)setEmailError('L’adresse du compte n’a pas pu être préremplie. Vous pouvez la saisir ci-dessous.')});
    return()=>{active=false};
  },[scope]);
  return <div className="contact-page">
    <section className="card contact-compose"><div className="contact-intro"><span className="contact-intro-icon"><Mail size={25}/></span><div><span className="eyebrow">EN CONTACT AVEC PIERIG</span><h2>Un bug, une idée, une envie ?</h2><p>Votre retour aide à faire évoluer l’atelier. Expliquez ce qui compte pour vous.</p></div></div>
      {emailError&&<p className="contact-field-help">{emailError}</p>}<ContactForm key={scope} csrf={props.d.csrf} email={email} onDone={()=>void history.load()}/>
    </section>
    <section className="card contact-history" aria-labelledby="contact-history-title"><div className="contact-section-heading"><div><span className="eyebrow">LE SUIVI DE VOS MESSAGES</span><h2 id="contact-history-title">Votre historique</h2></div><button type="button" className="button secondary" disabled={history.loading} onClick={()=>void history.load()}><RefreshCw size={16}/>Actualiser</button></div>
      <p>Vos messages envoyés depuis ce compte et leur état de traitement.</p>
      {history.error&&<p className="notice error" role="alert">{history.error}</p>}{history.loading&&<p role="status">Chargement de vos messages…</p>}
      {!history.loading&&!history.error&&!history.items.length&&<div className="contact-empty"><Inbox size={28}/><h3>Votre premier échange commence ici.</h3><p>Les messages que vous envoyez depuis ce compte apparaîtront dans cet espace.</p></div>}
      <div className="contact-ticket-list">{history.items.map(ticket=><Ticket key={ticket.id} ticket={ticket}/>)}</div>
      {history.hasMore&&<button type="button" className="button secondary" disabled={history.loading} onClick={()=>void history.load(history.items.length)}>Voir les messages plus anciens</button>}
    </section>
    {props.d.user.admin&&<ContactInbox {...props} onChanged={()=>void history.load()}/>}
  </div>;
}

export function ContactInbox({d,act,busy,onChanged}:Actions&{onChanged?:()=>void}) {
  const scope=d.user.username+':'+d.csrf,resource=useTickets('/contact/admin',scope),[saving,setSaving]=useState(''),[error,setError]=useState('');
  const current=useRef(scope),mounted=useRef(false);current.current=scope;
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[]);
  const update=async(ticket:ContactTicket,status:ContactStatus)=>{
    setSaving(ticket.id);setError('');
    try {
      await act('/contact/status',{ticket_id:ticket.id,expected_revision:ticket.revision,status},'Suivi du message enregistré');
      if(mounted.current&&current.current===scope){await resource.load();onChanged?.()}
    } catch(error) {if(mounted.current&&current.current===scope)setError(errorText(error))}
    finally {if(mounted.current&&current.current===scope)setSaving('')}
  };
  return <section className="card contact-admin" aria-labelledby="contact-inbox-title"><div className="contact-section-heading"><div><span className="eyebrow">ADMINISTRATION</span><h2 id="contact-inbox-title">La boîte de réception</h2></div><button type="button" className="button secondary" disabled={resource.loading||Boolean(saving)} onClick={()=>{setError('');void resource.load()}}><RefreshCw size={16}/>Recharger la boîte</button></div>
    <p>Les messages volontairement transmis par les visiteurs et les managers. Les changements de suivi sont visibles par leurs auteurs connectés.</p>
    {(resource.error||error)&&<p className="notice error" role="alert">{error||resource.error}</p>}{resource.loading&&<p role="status">Chargement de la boîte…</p>}
    {!resource.loading&&!resource.error&&!resource.items.length&&<div className="contact-empty"><Inbox size={28}/><h3>La boîte est à jour.</h3><p>Aucun message reçu pour le moment.</p></div>}
    <div className="contact-ticket-list">{resource.items.map(ticket=><Ticket key={ticket.id} ticket={ticket} admin><label className="contact-status-edit">Suivi de « {ticket.subject} »<select value={ticket.status} disabled={busy||resource.loading||Boolean(saving)} onChange={event=>void update(ticket,event.target.value as ContactStatus)}>{Object.entries(statusNames).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label></Ticket>)}</div>
    {resource.hasMore&&<button type="button" className="button secondary" disabled={resource.loading||Boolean(saving)} onClick={()=>void resource.load(resource.items.length)}>Voir les messages plus anciens</button>}
  </section>;
}
