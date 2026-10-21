import type { Clock, Fact, MatchInfo } from './api';

export const pct = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`;

export const num = (v: number, digits = 1) =>
  Number.isFinite(v) ? v.toFixed(digits) : '–';

export function clockText(c: Clock | null, fallbackMinute: number): string {
  if (!c) return `${String(fallbackMinute).padStart(2, '0')}:00`;
  return `${String(c.minute).padStart(2, '0')}:${String(c.second).padStart(2, '0')}`;
}

/** "momentum_shift" -> "Momentum shift" */
export function humanKind(kind: string): string {
  const s = kind.replace(/_/g, ' ').replace(/\bxg\b/gi, 'xG').replace(/\bvar\b/gi, 'VAR').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function subjectName(f: Fact, info: MatchInfo | null): string {
  if (f.subject_kind === 'match' || !info) return f.subject_kind === 'match' ? 'Match' : f.subject_id;
  for (const t of [info.home, info.away]) {
    if (t.team_id === f.subject_id) return t.name;
    const p = t.squad.find((x) => x.player_id === f.subject_id);
    if (p) return `${p.name} (${t.short})`;
  }
  return f.subject_id;
}

export function factValue(f: Fact): string {
  if (typeof f.value === 'number') {
    const v = Number.isInteger(f.value) ? String(f.value) : Math.abs(f.value) < 10 ? f.value.toFixed(2) : f.value.toFixed(1);
    return f.unit ? `${v} ${f.unit}` : v;
  }
  return f.unit ? `${f.value} ${f.unit}` : String(f.value);
}

export function seqOf(eventId: string): number | null {
  const m = /:(\d+)$/.exec(eventId);
  return m && m[1] ? parseInt(m[1], 10) : null;
}
