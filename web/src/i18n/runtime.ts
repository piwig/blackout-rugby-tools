import {languageTags, normalizeLocale, translate, type Locale, type MessageParams} from './core.ts';

const storageKey='brt-language';
function initialLocale():Locale {try{return normalizeLocale(localStorage.getItem(storageKey));}catch{return 'fr';}}
let currentLocale:Locale=initialLocale();
const listeners=new Set<()=>void>();
let catalogs:Partial<Record<Locale,Record<string,string>>>={};
export function installCatalogs(value:Partial<Record<Locale,Record<string,string>>>){catalogs=value;}
export const getLocale=()=>currentLocale;
export const localeTag=()=>languageTags[currentLocale];
export function setLocale(value:unknown):void {
  const next=normalizeLocale(value);
  try{localStorage.setItem(storageKey,next);}catch{/* The preference still works without browser storage. */}
  if(next===currentLocale)return;
  currentLocale=next;
  for(const listener of listeners)listener();
}
export function subscribeLocale(listener:()=>void){listeners.add(listener);return()=>{listeners.delete(listener);};}
export function tr(source:string,params?:MessageParams):string{return translate(catalogs[currentLocale]??{},source,params);}
