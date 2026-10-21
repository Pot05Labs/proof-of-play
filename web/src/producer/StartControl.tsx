import { useState, type FormEvent } from 'react';
import { api, ApiError } from '../lib/api';

export function StartControl({ pkey, onStarted }: { pkey: string; onStarted: () => void }) {
  const [seed, setSeed] = useState(7);
  const [speed, setSpeed] = useState(1);
  const [varOverturn, setVarOverturn] = useState(true);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setStatus(null);
    try {
      const r = await api.start(pkey, { seed, speed, var_overturn: varOverturn });
      setStatus({ ok: true, text: `Broadcast started: ${r.match_id} at ${speed}x.` });
      onStarted();
    } catch (err) {
      const text =
        err instanceof ApiError && err.status === 409
          ? 'A broadcast is already running. Wait for full time before starting another.'
          : err instanceof ApiError && err.status === 403
            ? 'The producer key was refused.'
            : 'The broadcast did not start. Check the API log.';
      setStatus({ ok: false, text });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel" aria-labelledby="start-h">
      <h2 id="start-h">Broadcast</h2>
      <form className="start-form" onSubmit={submit}>
        <label>
          Match seed
          <input type="number" min={0} step={1} value={seed} onChange={(e) => setSeed(Number(e.target.value))} />
        </label>
        <label>
          Speed
          <input type="number" min={0.1} max={120} step={0.1} value={speed} onChange={(e) => setSpeed(Number(e.target.value))} />
        </label>
        <label className="check">
          <input type="checkbox" checked={varOverturn} onChange={(e) => setVarOverturn(e.target.checked)} />
          VAR overturns a goal
        </label>
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? 'Starting' : 'Start broadcast'}
        </button>
      </form>
      {status && (
        <p className={`status-line${status.ok ? '' : ' err'}`} role="status">
          {status.text}
        </p>
      )}
    </section>
  );
}
