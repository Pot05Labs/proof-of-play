import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { api, ApiError, type MatchInfo, type ProducerView } from '../lib/api';
import { Wordmark } from '../ui/Wordmark';
import { ExperimentPanel } from './ExperimentPanel';
import { InsightLog } from './InsightLog';
import { LiveSystem } from './LiveSystem';
import { StartControl } from './StartControl';

const KEY = 'pop.producerKey';
const POLL_MS = 2000;

function readKey(): string {
  try {
    return sessionStorage.getItem(KEY) ?? '';
  } catch {
    return '';
  }
}

function KeyGate({ onKey, error }: { onKey: (k: string) => void; error: string | null }) {
  const [value, setValue] = useState('');
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim()) onKey(value.trim());
  };
  return (
    <main className="gate">
      <Wordmark />
      <h1>Producer console</h1>
      <p>Enter the producer key to see every insight the system wrote and the live experiment readout.</p>
      <form onSubmit={submit}>
        <label htmlFor="pkey">Producer key</label>
        <input id="pkey" type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} />
        <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
          Open console
        </button>
        {error && <p className="form-error" role="alert">{error}</p>}
      </form>
    </main>
  );
}

export default function ProducerApp() {
  const [key, setKey] = useState(readKey);
  const [view, setView] = useState<ProducerView | null>(null);
  const [gateError, setGateError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const [info, setInfo] = useState<MatchInfo | null>(null);

  useEffect(() => {
    api.match().then(setInfo).catch(() => undefined);
  }, [key]);

  const saveKey = (k: string) => {
    try {
      sessionStorage.setItem(KEY, k);
    } catch {
      /* ignore */
    }
    setGateError(null);
    setKey(k);
  };

  const signOut = useCallback((msg: string | null) => {
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
    setKey('');
    setView(null);
    setGateError(msg);
  }, []);

  const load = useCallback(async () => {
    if (!key) return;
    try {
      setView(await api.producer(key));
      setOffline(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) signOut('That key was not accepted. Check POP_ADMIN_KEY on the server.');
      else setOffline(true);
    }
  }, [key, signOut]);

  useEffect(() => {
    if (!key) return;
    void load();
    const id = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(id);
  }, [key, load]);

  if (!key) return <KeyGate onKey={saveKey} error={gateError} />;

  return (
    <div className="console">
      <header className="console-head">
        <Wordmark />
        <h1>Producer console</h1>
        <span className="head-spacer" />
        <button type="button" className="btn btn-small btn-ghost" onClick={() => signOut(null)}>
          Lock console
        </button>
      </header>
      {offline && <p className="banner" role="alert">The API is not responding. Retrying every 2 seconds.</p>}
      <LiveSystem view={view} />
      <div className="console-grid">
        <div style={{ display: 'grid', gap: 16, minWidth: 0 }}>
          <StartControl pkey={key} onStarted={() => void load()} />
          <ExperimentPanel pkey={key} />
        </div>
        <InsightLog rows={view?.insights ?? []} info={info} />
      </div>
    </div>
  );
}
