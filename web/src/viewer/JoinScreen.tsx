import { useEffect, useId, useMemo, useState, type FormEvent } from 'react';
import { api, type Audience, type Language, type MatchInfo } from '../lib/api';
import { labels, LANGUAGES } from '../lib/i18n';
import { Wordmark } from '../ui/Wordmark';
import type { ViewerSession } from './session';

export const CONSENT_LINE =
  'We record anonymous viewing activity, no names, to test whether personalised insights help. You may see one of two versions.';

interface Props {
  onJoined: (s: ViewerSession) => void;
  sessionLost: boolean;
}

export function JoinScreen({ onJoined, sessionLost }: Props) {
  const [info, setInfo] = useState<MatchInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [mode, setMode] = useState<Audience>('fan');
  const [club, setClub] = useState<string>('');
  const [player, setPlayer] = useState<string>('');
  const [language, setLanguage] = useState<Language>('en');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const t = labels(language);
  const ids = { player: useId(), lang: useId() };

  useEffect(() => {
    let alive = true;
    api
      .match()
      .then((m) => {
        if (!alive) return;
        setInfo(m);
        setClub(m.home.team_id);
      })
      .catch(() => alive && setLoadError('unreachable'));
    return () => {
      alive = false;
    };
  }, []);

  const squad = useMemo(() => {
    if (!info) return [];
    const team = [info.home, info.away].find((x) => x.team_id === club);
    return team ? [...team.squad].sort((a, b) => a.number - b.number) : [];
  }, [info, club]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const body = {
        consent: true as const,
        mode,
        club_id: club || null,
        player_id: player || null,
        language,
      };
      const { session_id } = await api.createSession(body);
      onJoined({ session_id, mode, club_id: body.club_id, player_id: body.player_id, language });
    } catch {
      setError(t.joinError);
      setBusy(false);
    }
  };

  return (
    <main className="join">
      <div className="join-inner">
        <Wordmark />
        <h1 className="display">
          {info ? (
            <>
              {info.home.name}
              <br />
              <span style={{ color: 'var(--mist)' }}>v</span> {info.away.name}
            </>
          ) : (
            t.tonightsMatch
          )}
        </h1>
        <p className="fixture">
          {info ? (
            <>
              <strong>{info.competition}</strong>, {info.venue}. {t.fixtureTail}
            </>
          ) : loadError ? (
            <span className="form-error" role="alert">{t.loadError}</span>
          ) : (
            t.loading
          )}
        </p>

        {sessionLost && (
          <p className="form-error" role="status">
            {t.sessionLost}
          </p>
        )}

        <form onSubmit={submit}>
          <fieldset>
            <legend>{t.howWatch}</legend>
            <div className="choice-row">
              {(['fan', 'analyst'] as const).map((m) => (
                <label key={m} className="choice">
                  <input type="radio" name="mode" value={m} checked={mode === m} onChange={() => setMode(m)} />
                  <span className="choice-title">{m === 'fan' ? t.casual : t.analyst}</span>
                  <span className="choice-hint">{m === 'fan' ? t.casualHint : t.analystHint}</span>
                </label>
              ))}
            </div>
          </fieldset>

          {info && (
            <fieldset>
              <legend>{t.club}</legend>
              <div className="choice-row">
                {[info.home, info.away].map((team) => (
                  <label key={team.team_id} className="choice club-choice">
                    <input
                      type="radio"
                      name="club"
                      value={team.team_id}
                      checked={club === team.team_id}
                      onChange={() => {
                        setClub(team.team_id);
                        setPlayer('');
                      }}
                    />
                    <span className="swatch" style={{ background: team.colour }} aria-hidden="true" />
                    <span className="choice-title">{team.name}</span>
                    <span className="choice-hint">{team.short}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}

          {info && (
            <fieldset>
              <label className="field-label" htmlFor={ids.player}>
                {t.player}
              </label>
              <select id={ids.player} className="select" value={player} onChange={(e) => setPlayer(e.target.value)}>
                <option value="">{t.noPlayer}</option>
                {squad.map((p) => (
                  <option key={p.player_id} value={p.player_id}>
                    {p.number}. {p.name}, {p.position}
                  </option>
                ))}
              </select>
            </fieldset>
          )}

          <fieldset>
            <label className="field-label" htmlFor={ids.lang}>
              {t.language}
            </label>
            <select
              id={ids.lang}
              className="select"
              value={language}
              onChange={(e) => setLanguage(e.target.value as Language)}
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code} lang={l.code}>
                  {l.name}
                </option>
              ))}
            </select>
          </fieldset>

          <div className="consent">
            <p lang="en">{CONSENT_LINE}</p>
            <button type="submit" className="btn btn-primary" disabled={busy || !info}>
              {busy ? t.joining : t.join}
            </button>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
          </div>
        </form>
      </div>
    </main>
  );
}
