export type VacationObjective = 'balanced' | 'recovery' | 'development';
export type VacationEnergyScale = 'auto' | 'percent' | 'level';
export interface VacationOptions {
  objective: VacationObjective;
  energy_floor: number;
  energy_scale: VacationEnergyScale;
  excluded_ids: string[];
  captain_id: string | null;
  kicker_id: string | null;
}
export interface VacationRule extends VacationOptions {
  team_id: string;
  enabled: boolean;
  mode: 'prepare' | 'automatic';
  start_at: string | null;
  end_at: string | null;
  lead_hours: number;
  manage_existing: boolean;
  revision: number;
  paused_reason: string | null;
}
export interface VacationFixture {
  id: string;
  team_id: string;
  home_team_id: string;
  away_team_id: string;
  competition: string;
  match_start: string | null;
}
export type VacationPreviewStatus = 'ready' | 'blocked' | 'sending' | 'confirmed' | 'uncertain' | 'cancelled' | 'expired' | 'conflict' | 'reconciled';
export interface VacationPreview {
  id: string;
  team_id: string;
  fixture_id: string;
  source: 'optimized' | 'saved';
  status: VacationPreviewStatus;
  created_at: string;
  expires_at: string;
  revision: number;
  automatic: boolean;
  can_send: boolean;
  schema: string;
  bench_size: 7 | 8;
  verification_required: boolean;
  reconciliation_required?: boolean;
  current_payload?: Record<string, string> | null;
  payload: Record<string, string>;
  players: {id: string; name: string; slot: number; role?: string; energy?: number | null; reason?: string}[];
  changes: {field: string; before: string | null; after: string | null}[];
  warnings: string[];
  blocking_reasons: string[];
  deadline: string | null;
  rule: VacationOptions;
}
export interface VacationEvent {
  id: number;
  team_id: string;
  preview_id: string | null;
  kind: string;
  message: string;
  created_at: string;
}
export interface VacationStatus {
  rules: VacationRule[];
  previews: VacationPreview[];
  events: VacationEvent[];
  worker_interval_seconds: number;
  write_ready: boolean;
  write_blocked_reason?: string | null;
  worker_enabled: boolean;
  worker_last_run?: string | null;
  worker_error?: string | null;
}
