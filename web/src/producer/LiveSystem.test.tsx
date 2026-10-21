import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { ProducerView } from '../lib/api';
import { LiveSystem } from './LiveSystem';

afterEach(cleanup);

const base: ProducerView = {
  model: 'foundry:gpt-4.1-mini', llm_calls: 223, rejected_rewrites: 5, retracted: 0, total: 223,
  queue_depth: 0, profiles: 91, write_lag_ms_p50: 4213.9, write_lag_ms_p95: 12218.5,
  usage: { calls: 223, failures: 78, input_tokens: 187_275, output_tokens: 3_836, cached_input_tokens: 145_024 },
  store: { written: 2971, failed: 0, pending: 0 },
  insights: [],
};

const cell = (label: string) => screen.getByText(label).parentElement!;

describe('LiveSystem', () => {
  it('shows model, counts, lag, cache share and the estimated cost', () => {
    render(<LiveSystem view={base} />);
    expect(screen.getByText('gpt-4.1-mini')).toBeTruthy();
    expect(screen.getByText('foundry')).toBeTruthy();
    expect(within(cell('Insights written')).getByText('223')).toBeTruthy();
    expect(within(cell('Viewer profiles')).getByText('91')).toBeTruthy();
    expect(within(cell('Write lag p50')).getByText('4,214 ms')).toBeTruthy();
    expect(within(cell('Write lag p95')).getByText('12,219 ms')).toBeTruthy();
    expect(screen.getByText('77%')).toBeTruthy();
    expect(screen.getByText('US$0.0375')).toBeTruthy();
    expect(screen.getByText(/est\. spend/)).toBeTruthy();
    expect(cell('Rewrites rejected').className).toContain('alarm');
  });

  it('renders nulls as dashes and never prints NaN', () => {
    const { container } = render(
      <LiveSystem view={{ ...base, write_lag_ms_p50: null, write_lag_ms_p95: null, usage: null, store: null }} />,
    );
    expect(within(cell('Write lag p50')).getByText('-')).toBeTruthy();
    expect(within(cell('Write lag p95')).getByText('-')).toBeTruthy();
    expect(screen.getByText('No usage reported by this model client.')).toBeTruthy();
    expect(screen.getByText('No database configured.')).toBeTruthy();
    expect(container.textContent).not.toMatch(/NaN|undefined|Infinity/);
  });

  it('survives an older server that omits the new fields', () => {
    const old = { model: 'stub', llm_calls: 0, rejected_rewrites: 0, retracted: 0, insights: [] } as unknown as ProducerView;
    const { container } = render(<LiveSystem view={old} />);
    expect(container.textContent).not.toMatch(/NaN|undefined/);
  });

  it('renders before the first poll', () => {
    const { container } = render(<LiveSystem view={null} />);
    expect(container.textContent).not.toMatch(/NaN|undefined/);
  });

  it('warns on the database group when writes fail or back up', () => {
    const { rerender } = render(<LiveSystem view={base} />);
    const group = () => screen.getByRole('group', { name: 'Database' });
    expect(group().className).not.toContain('warn');
    rerender(<LiveSystem view={{ ...base, store: { written: 10, failed: 2, pending: 0 } }} />);
    expect(group().className).toContain('warn');
    expect(screen.getByText(/2 writes failed/)).toBeTruthy();
    rerender(<LiveSystem view={{ ...base, store: { written: 10, failed: 0, pending: 101 } }} />);
    expect(group().className).toContain('warn');
    expect(cell('Pending').className).toContain('alarm');
    rerender(<LiveSystem view={{ ...base, store: { written: 10, failed: 0, pending: 0, dropped_queue_full: 4, container: 'loadtest' } }} />);
    expect(group().className).toContain('warn');
    expect(cell('Dropped').className).toContain('alarm');
    expect(screen.getByText('loadtest')).toBeTruthy();
  });
});
