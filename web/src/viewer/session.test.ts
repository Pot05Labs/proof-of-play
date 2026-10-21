import { beforeEach, describe, expect, it } from 'vitest';
import { isProducerPath } from '../App';
import { clearSession, loadSession, saveSession } from './session';

beforeEach(() => sessionStorage.clear());

describe('viewer session storage', () => {
  it('round-trips only what the viewer chose, never an arm', () => {
    saveSession({ session_id: 'abc', mode: 'analyst', club_id: 'h', player_id: null, language: 'zu' });
    const raw = JSON.parse(sessionStorage.getItem('pop.session')!);
    expect(Object.keys(raw).sort()).toEqual(['club_id', 'language', 'mode', 'player_id', 'session_id']);
    expect(loadSession()).toEqual({ session_id: 'abc', mode: 'analyst', club_id: 'h', player_id: null, language: 'zu' });
  });

  it('rejects junk and normalises unknown values', () => {
    sessionStorage.setItem('pop.session', '{not json');
    expect(loadSession()).toBeNull();
    sessionStorage.setItem('pop.session', JSON.stringify({ session_id: 'x', mode: 'casual', language: 'fr' }));
    expect(loadSession()).toMatchObject({ mode: 'fan', language: 'en', club_id: null });
    clearSession();
    expect(loadSession()).toBeNull();
  });
});

describe('routes', () => {
  it('recognises the producer console path only', () => {
    expect(isProducerPath('/producer')).toBe(true);
    expect(isProducerPath('/producer/')).toBe(true);
    expect(isProducerPath('/')).toBe(false);
    expect(isProducerPath('/producers')).toBe(false);
  });
});
