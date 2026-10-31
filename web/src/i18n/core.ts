export const locales = ['fr', 'en', 'es', 'it'] as const;
export type Locale = typeof locales[number];
export const languageNames:Record<Locale,string> = {fr:'Français', en:'English', es:'Español', it:'Italiano'};
export const languageTags:Record<Locale,string> = {fr:'fr-FR', en:'en-GB', es:'es-ES', it:'it-IT'};
export function normalizeLocale(value:unknown):Locale {
  return typeof value==='string' && (locales as readonly string[]).includes(value) ? value as Locale : 'fr';
}
export type MessageParams = Record<string,string|number>;
export function translate(catalog:Record<string,string>, source:string, params:MessageParams={}):string {
  const message=Object.hasOwn(catalog,source) ? catalog[source] : source;
  // Only the template is looked up. Names, notes and other parameter data stay intact.
  return message.replace(/\{([A-Za-z][A-Za-z0-9_]*)\}/g,(token,key)=>Object.hasOwn(params,key)?String(params[key]):token);
}
