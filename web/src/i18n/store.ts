/// <reference types="vite/client" />
import {useSyncExternalStore} from 'react';
import {type Locale} from './core';
import {installCatalogs,getLocale,setLocale,subscribeLocale} from './runtime';

const bundles=import.meta.glob<Record<string,string>>('./locales/*.json',{eager:true,import:'default'});
installCatalogs(Object.fromEntries(Object.entries(bundles).map(([path,catalog])=>[path.split('/').pop()!.replace('.json',''),catalog])));
export {getLocale,setLocale,localeTag,tr} from './runtime';
export function useLocale(){const locale=useSyncExternalStore(subscribeLocale,getLocale,()=> 'fr' as Locale);return {locale,setLocale};}
