import {localeTag} from './i18n/runtime.ts';

/** Keep the four decimal places used by observation deltas visible in tables. */
export function formatStatistic(value:unknown):string {
  if(typeof value==='number')return Number.isFinite(value)?new Intl.NumberFormat(localeTag(),{maximumFractionDigits:4}).format(Object.is(value,-0)?0:value):'—';
  return value===undefined||value===null||value===''?'—':String(value);
}
