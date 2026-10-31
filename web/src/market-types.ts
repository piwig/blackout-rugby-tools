import type {skillKeys,roleNames} from './role-weights-model';

export type MarketSkill=typeof skillKeys[number];
export type MarketRole=typeof roleNames[number];
export type MarketPlan={cash:number|null;weekly_income:number|null;weekly_expenses:number|null;reserve:number|null;committed_bids:number|null;complete:boolean;observed_at:string|null};
export type MarketCandidate={id:string;name:string;classic_id:string|null;role:MarketRole;age:number|null;price:number|null;weekly_salary:number|null;fees:number|null;skills:Record<MarketSkill,number|null>;notes:string;status:'watch'|'shortlist'|'dismissed'};
export type MarketInvestment={id:string;name:string;initial_cost:number|null;weekly_cost:number|null;notes:string};
export type MarketDraft={plan:MarketPlan;candidates:MarketCandidate[];investments:MarketInvestment[]};
export type MarketScenario={id:string;status:'unknown'|'affordable'|'over_budget';missing_fields:string[];warnings:string[];initial_cost:number|null;four_week_cost:number|null;immediate_headroom:number|null;projected_cash:number|null;projected_headroom:number|null;purchase_ceiling:number|null};
export type MarketComparison={role:string;score:number|null;known_skills:number;missing_skills:string[];squad_known:number;squad_total:number;squad_best:number|null;squad_average:number|null;delta_best:number|null;rank:number|null};
export type MarketAnalysis={horizon_weeks:4;confirmed:boolean;missing_fields:string[];warnings:string[];base:{weekly_net:number|null;projected_cash:number|null;immediate_headroom:number|null;projected_headroom:number|null;purchase_ceiling:number|null};squad:{snapshot_id:number|null;observed_at:string|null;total:number;criteria_method:'weighted-average-v1'};candidates:(MarketScenario&{comparison:MarketComparison})[];investments:MarketScenario[]};
export type MarketDocument=MarketDraft&{revision:number;updated_at:string|null;analysis:MarketAnalysis};
