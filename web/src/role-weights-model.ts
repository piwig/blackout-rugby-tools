export const skillKeys = ['stamina','handling','attack','defense','technique','strength','jumping','speed','agility','kicking'] as const;
export const roleNames = ['Pilier','Talonneur','Deuxième ligne','Troisième ligne','Demi de mêlée','Demi d’ouverture','Centre','Ailier','Arrière'] as const;
export type RoleWeights = Record<string,Record<string,number>>;
export const weightMethod = 'weighted-average-v1' as const;
export type WeightCriteria = {role_weights?: RoleWeights; weight_profile_name?: string; weight_method?: typeof weightMethod};

export function validRoleWeights(value: unknown): value is RoleWeights {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const roles = value as Record<string,unknown>;
  return Object.keys(roles).length === roleNames.length && roleNames.every(role => {
    const w = roles[role];
    if (!w || typeof w !== 'object' || Array.isArray(w)) return false;
    const weights = w as Record<string,unknown>;
    return Object.keys(weights).length === skillKeys.length && skillKeys.every(skill =>
      typeof weights[skill] === 'number' && Number.isInteger(weights[skill]) && (weights[skill] as number) >= 0 && (weights[skill] as number) <= 10)
      && skillKeys.reduce((sum,skill)=>sum+(weights[skill] as number),0) > 0;
  });
}

export function changeRoleWeight(weights: RoleWeights, role: string, skill: string, value: number): RoleWeights {
  return {...weights,[role]:{...weights[role],[skill]:value}};
}

export function roleCoverage(players: Record<string,unknown>[], weights: Record<string,number>) {
  const required = Object.entries(weights).filter(([,value])=>value>0).map(([skill])=>skill);
  return {known: players.filter(player=>required.length>0 && required.every(skill=>{
    const value=player[skill];
    return value !== null && value !== undefined && typeof value !== 'boolean' && String(value).trim()!=='' && Number.isFinite(Number(String(value).replace(',','.')));
  })).length,total:players.length};
}
