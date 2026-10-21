import type { Audience, Language } from '../lib/api';
import { isLanguage } from '../lib/i18n';

// The arm is never known to the client. Only what the viewer chose is stored.
export interface ViewerSession {
  session_id: string;
  mode: Audience;
  club_id: string | null;
  player_id: string | null;
  language: Language;
}

const KEY = 'pop.session';

export function loadSession(): ViewerSession | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Partial<ViewerSession>;
    if (typeof s.session_id !== 'string' || !s.session_id) return null;
    return {
      session_id: s.session_id,
      mode: s.mode === 'analyst' ? 'analyst' : 'fan',
      club_id: typeof s.club_id === 'string' ? s.club_id : null,
      player_id: typeof s.player_id === 'string' ? s.player_id : null,
      language: typeof s.language === 'string' && isLanguage(s.language) ? s.language : 'en',
    };
  } catch {
    return null;
  }
}

export function saveSession(s: ViewerSession): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* storage blocked: the session still works for this page view */
  }
}

export function clearSession(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
