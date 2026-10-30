import {useRef, useState} from 'react';
import {ArrowLeft, ArrowRight, ShieldCheck} from 'lucide-react';
import {request} from './App';
import {AvatarChoices, type AvatarStyle} from './profile';
import {AntiBot} from './antibot';
import './registration.css';

export function RegistrationForm({onRegistered,onCancel}:{onRegistered:()=>Promise<void>;onCancel:()=>void}) {
  const [username,setUsername]=useState(''),[password,setPassword]=useState(''),[email,setEmail]=useState('');
  const [avatar,setAvatar]=useState<AvatarStyle>('jersey'),[website,setWebsite]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[created,setCreated]=useState(false);
  const [captchaToken,setCaptchaToken]=useState<string|null>(null),[captchaReset,setCaptchaReset]=useState(0);
  const submitting=useRef(false);
  const submit=async()=>{
    if(submitting.current||(!created&&captchaToken===null))return;
    submitting.current=true;setBusy(true);setError('');
    let registered=created;
    try {
      if(!registered){
        const result=await request('/register',{username,password,email,avatar_style:avatar,website,captcha_token:captchaToken||''});
        registered=true;setCreated(true);setPassword('');
        try{localStorage.setItem('brt-username',result.user.username)}catch{/* Storage preferences are optional. */}
      }
      await onRegistered();
    } catch(caught) {
      setError(registered?'Votre compte est créé. Réessayez d’ouvrir votre espace ou revenez à la connexion.':caught instanceof Error?caught.message:'L’inscription n’a pas abouti. Réessayez.');
    } finally {submitting.current=false;setBusy(false);setCaptchaToken(null);setCaptchaReset(value=>value+1)}
  };
  return <section className="registration-panel" aria-labelledby="registration-heading">
    <button type="button" className="registration-back" disabled={busy} onClick={onCancel}><ArrowLeft size={16}/>Retour à la connexion</button>
    <span className="eyebrow">VOTRE PLACE DANS L’ATELIER</span>
    <h2 id="registration-heading">Créez votre espace.</h2>
    <p>Quelques repères pour commencer. Vous ajouterez ensuite vos clubs.</p>
    <form className="registration-form" onSubmit={event=>{event.preventDefault();void submit()}}>
      {!created&&<>
        <fieldset className="registration-fields" disabled={busy}>
          <label>Identifiant<input required autoComplete="username" autoCapitalize="none" spellCheck={false} minLength={3} maxLength={40} pattern="[A-Za-z0-9][A-Za-z0-9_.\-]{2,39}" value={username} onChange={event=>setUsername(event.target.value)} aria-describedby="registration-username-hint"/><small id="registration-username-hint">3 à 40 caractères : lettres, chiffres, point, tiret ou underscore.</small></label>
          <label>Adresse e-mail<input required type="email" autoComplete="email" maxLength={254} value={email} onChange={event=>setEmail(event.target.value)} aria-describedby="registration-email-hint"/><small id="registration-email-hint">Conservée dans votre compte privé.</small></label>
          <label>Mot de passe de l’outil<input required type="password" autoComplete="new-password" minLength={12} maxLength={128} value={password} onChange={event=>setPassword(event.target.value)} aria-describedby="registration-password-hint"/><small id="registration-password-hint">12 à 128 caractères. Choisissez un mot de passe pour BRT.</small></label>
          <div className="registration-honeypot" aria-hidden="true"><label>Site web<input name="website" autoComplete="off" tabIndex={-1} maxLength={200} value={website} onChange={event=>setWebsite(event.target.value)}/></label></div>
        </fieldset>
        <fieldset className="registration-avatar" disabled={busy}><legend>Un avatar ? <span>Facultatif</span></legend><AvatarChoices value={avatar} onChange={setAvatar} name="registration-avatar"/><small>Maillot par défaut. Vous pourrez le changer dans votre profil.</small></fieldset>
        <AntiBot action="register" onToken={setCaptchaToken} resetKey={captchaReset}/>
      </>}
      {error&&<p className="text-error" role="alert">{error}</p>}
      <button className="button primary" disabled={busy||(!created&&captchaToken===null)}>{busy?'Ouverture de votre espace…':created?'Ouvrir mon espace':'Créer mon compte'}<ArrowRight size={17}/></button>
    </form>
    <div className="login-foot"><ShieldCheck size={17}/><span>Votre compte BRT est distinct de celui du jeu Blackout Rugby.</span></div>
  </section>;
}
