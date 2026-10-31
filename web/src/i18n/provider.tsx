import {useLayoutEffect, type ReactNode} from 'react';
import {languageNames,locales,type Locale} from './core';
import {setLocale,tr,useLocale} from './store';
import './language.css';

export function LanguageProvider({children}:{children:ReactNode}) {
  const {locale}=useLocale();
  useLayoutEffect(()=>{document.documentElement.lang=locale;},[locale]);
  return children;
}

export function LanguageSelect({value,onChange,disabled=false,compact=false}:{value?:Locale;onChange?:(locale:Locale)=>void;disabled?:boolean;compact?:boolean}) {
  const {locale}=useLocale();
  return <label className={'language-select'+(compact?' language-select-compact':'')}><span>{tr('Langue')}</span><select aria-label={tr('Langue de l’interface')} value={value??locale} disabled={disabled} onChange={event=>(onChange??setLocale)(event.target.value as Locale)}>{locales.map(code=><option key={code} value={code} lang={code}>{languageNames[code]}</option>)}</select></label>;
}
