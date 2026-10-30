export type OptimizationObjective = 'balanced' | 'recovery' | 'development';
export type OptimizationCategory = 'squad' | 'training' | 'academy' | 'season' | 'stadium' | 'data';
export type OptimizationPriority = 'high' | 'medium' | 'low';

export interface OptimizationReport {
  team: {id: string; name: string; country: string};
  objective: OptimizationObjective;
  season: number;
  generated_at: string;
  sources: {squad: string | null; academy: string | null};
  warnings: string[];
  summary: {seniors: number; academy: number; eligible: number; selected: number; low_energy: number; unknown_energy: number};
  lineup: {
    slots: Record<string, string>;
    players: {slot: number; role: string; id: string; name: string; score: number; energy: number | null; reason: string}[];
    unfilled: number[];
    excluded: {id: string; name: string; reason: string}[];
    comparison: {saved_score: number | null; proposed_score: number | null; delta: number | null};
  };
  recommendations: {
    id: string; category: OptimizationCategory; priority: OptimizationPriority;
    title: string; detail: string; evidence: string[]; page: string;
  }[];
  training: {
    priorities: {skill: string; label: string; average: number; count: number; reason: string}[];
    grid: string[][]; added: number; preserved: number; remaining_weeks: number; start_week: number;
  };
  season_plan: {phase: string; weeks: string; actions: string[]}[];
  matches: {
    id: string; type: number; home: string; away: string; coverage: number;
    classified: number; total: number; inferred: number;
    sides: {side: 'home' | 'away'; name: string; dominant: string | null; share: number | null; actions: number; advice: string[]; evidence: string[]}[];
  }[];
  methodology: string[];
}
