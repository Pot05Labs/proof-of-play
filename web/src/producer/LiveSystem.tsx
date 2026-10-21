import type { ProducerView } from '../lib/api';
import {
  DASH, PRICE_PER_M, STORE_PENDING_ALARM, cacheShare, estimateUsd, failureShare, fmtInt, fmtMs, fmtShare,
  fmtTokens, fmtUsd, splitModel, storeAlarm,
} from './meters';

const n = (v: number | null | undefined) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

function Readout({ k, v, alarm, sub }: { k: string; v: string; alarm?: boolean; sub?: string }) {
  return (
    <div className={`ops-cell${alarm ? ' alarm' : ''}`}>
      <div className="k">{k}</div>
      <div className="n">{v}</div>
      {sub && <div className="s">{sub}</div>}
    </div>
  );
}

/** Lag strip: p50 marker and p50..p95 band on a 0..scale ms track. */
function LagMeter({ p50, p95 }: { p50: number | null; p95: number | null }) {
  const scale = Math.max(1000, (p95 ?? p50 ?? 0) * 1.2);
  const at = (v: number) => `${Math.min(100, (v / scale) * 100)}%`;
  const label = p50 === null ? 'No writes timed yet.' : `Write lag median ${fmtMs(p50)}, 95th percentile ${fmtMs(p95)}.`;
  return (
    <div className="lag" role="img" aria-label={label}>
      <div className="lag-track">
        {p50 !== null && p95 !== null && (
          <span className="lag-band" style={{ left: at(p50), width: `calc(${at(p95)} - ${at(p50)})` }} />
        )}
        {p50 !== null && <span className="lag-p50" style={{ left: at(p50) }} />}
      </div>
      <div className="lag-scale"><span>0</span><span>{fmtMs(scale)}</span></div>
    </div>
  );
}

export function LiveSystem({ view }: { view: ProducerView | null }) {
  const usage = view?.usage ?? null;
  const store = view?.store ?? null;
  const p50 = n(view?.write_lag_ms_p50);
  const p95 = n(view?.write_lag_ms_p95);
  const share = cacheShare(usage);
  const cost = estimateUsd(usage);
  const fail = failureShare(usage);
  const rejected = n(view?.rejected_rewrites) ?? 0;
  const retracted = n(view?.retracted) ?? 0;
  const queue = n(view?.queue_depth);
  const dbAlarm = storeAlarm(store);
  const model = splitModel(view?.model);

  return (
    <section className="panel ops" aria-labelledby="ops-h">
      <header className="ops-head">
        <h2 id="ops-h">Live system</h2>
        <span className="ops-model" title={view?.model ?? undefined}>
          <i aria-hidden="true" />
          {model.provider && <span className="ops-provider">{model.provider}</span>}
          <strong>{model.name}</strong>
        </span>
      </header>

      <div className="ops-rack">
        <div className="ops-group" role="group" aria-labelledby="ops-out">
          <h3 id="ops-out">Output</h3>
          <div className="ops-row">
            <Readout k="Insights written" v={fmtInt(view?.total)} />
            <Readout k="Rewrites rejected" v={fmtInt(view ? rejected : null)} alarm={rejected > 0} />
            <Readout k="Retracted" v={fmtInt(view ? retracted : null)} alarm={retracted > 0} />
          </div>
        </div>

        <div className="ops-group" role="group" aria-labelledby="ops-pipe">
          <h3 id="ops-pipe">Pipeline</h3>
          <div className="ops-row">
            <Readout k="Queue depth" v={fmtInt(queue)} />
            <Readout k="Viewer profiles" v={fmtInt(view?.profiles)} />
          </div>
          <div className="ops-row">
            <Readout k="Write lag p50" v={fmtMs(p50)} />
            <Readout k="Write lag p95" v={fmtMs(p95)} />
          </div>
          <LagMeter p50={p50} p95={p95} />
        </div>

        <div className="ops-group" role="group" aria-labelledby="ops-model">
          <h3 id="ops-model">Model usage</h3>
          {usage ? (
            <>
              <div className="ops-row">
                <Readout k="Calls" v={fmtInt(usage.calls)} />
                <Readout k="Failed" v={fmtInt(usage.failures)} alarm={usage.failures > 0}
                  sub={fail === null ? undefined : `${fmtShare(fail)} of calls`} />
              </div>
              <div className="ops-row">
                <Readout k="Tokens in" v={fmtTokens(usage.input_tokens)} />
                <Readout k="Tokens out" v={fmtTokens(usage.output_tokens)} />
              </div>
              <div className="cache">
                <div className="cache-k">
                  <span>Input served from cache</span>
                  <strong>{fmtShare(share)}</strong>
                </div>
                <div className="cache-track" role="meter" aria-label="Input served from cache"
                  aria-valuemin={0} aria-valuemax={100} aria-valuenow={share === null ? undefined : Math.round(share * 100)}>
                  <span style={{ width: share === null ? '0%' : fmtShare(share, 1) }} />
                </div>
              </div>
              <p className="cost">
                <span className="cost-n">{fmtUsd(cost)}</span>
                <span className="cost-k">
                  est. spend at gpt-4.1-mini list price: US${PRICE_PER_M.input.toFixed(2)} in, US${PRICE_PER_M.cachedInput.toFixed(2)} cached in, US${PRICE_PER_M.output.toFixed(2)} out, per 1M tokens
                </span>
              </p>
            </>
          ) : (
            <p className="ops-empty">{view ? 'No usage reported by this model client.' : DASH}</p>
          )}
        </div>

        <div className={`ops-group${dbAlarm ? ' warn' : ''}`} role="group" aria-labelledby="ops-db">
          <h3 id="ops-db">Database</h3>
          {store ? (
            <>
              <div className="ops-row">
                <Readout k="Written" v={fmtInt(store.written)} />
                <Readout k="Pending" v={fmtInt(store.pending)} alarm={store.pending > STORE_PENDING_ALARM} />
                <Readout k="Failed" v={fmtInt(store.failed)} alarm={store.failed > 0} />
                {store.dropped_queue_full !== undefined && (
                  <Readout k="Dropped" v={fmtInt(store.dropped_queue_full)} alarm={store.dropped_queue_full > 0} />
                )}
              </div>
              {store.container && (
                <p className="ops-note">{store.database ? `${store.database} / ` : ''}{store.container}</p>
              )}
              {dbAlarm && (
                <p className="ops-warn" role="status">
                  {store.failed > 0 ? `${fmtInt(store.failed)} writes failed. ` : ''}
                  {store.pending > STORE_PENDING_ALARM ? `Write queue above ${STORE_PENDING_ALARM}. ` : ''}
                  {(store.dropped_queue_full ?? 0) > 0 ? `${fmtInt(store.dropped_queue_full)} writes dropped, queue full.` : ''}
                </p>
              )}
            </>
          ) : (
            <p className="ops-empty">{view ? 'No database configured.' : DASH}</p>
          )}
        </div>
      </div>
    </section>
  );
}
