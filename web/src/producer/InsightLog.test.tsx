import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { ProducerRow } from '../lib/api';
import { InsightLog } from './InsightLog';

afterEach(cleanup);

const row = (over: Partial<ProducerRow>): ProducerRow => ({
  insight_id: 'i', minute: 10, text: 'Fine sentence.', verified: true, notes: 'verified', retracted: false,
  audience: 'fan', language: 'en', club: null, player: null, latency_ms: 1.2, ...over,
});

describe('InsightLog', () => {
  const rows = [
    row({ insight_id: 'a', minute: 5, text: 'Early verified.' }),
    row({ insight_id: 'b', minute: 20, text: 'Grounded draft.', notes: 'model rewrite rejected (number 3 not in facts); published grounded draft' }),
    row({ insight_id: 'c', minute: 30, text: 'Goal for X.', retracted: true }),
  ];

  it('puts rejected model rewrites first, with the tag and the verifier note', () => {
    render(<InsightLog rows={rows} info={null} />);
    const body = screen.getAllByRole('rowgroup')[1]!;
    const trs = within(body).getAllByRole('row');
    expect(trs[0]!.textContent).toContain('Grounded draft.');
    expect(within(trs[0]!).getByText('Rewrite rejected')).toBeTruthy();
    expect(within(trs[0]!).getByText(/model rewrite rejected \(number 3 not in facts\)/)).toBeTruthy();
    expect(trs[0]!.className).toContain('rejected');
  });

  it('marks retracted rows and filters by kind', () => {
    render(<InsightLog rows={rows} info={null} />);
    fireEvent.click(screen.getByRole('button', { name: /Retracted \(1\)/ }));
    const body = screen.getAllByRole('rowgroup')[1]!;
    const trs = within(body).getAllByRole('row');
    expect(trs).toHaveLength(1);
    expect(within(trs[0]!).getByText('Retracted')).toBeTruthy();
  });

  it('opens the agent trace of one insight, marking the failed step', () => {
    const traced = row({
      insight_id: 't', text: 'Repaired sentence.', notes: 'repaired by Editor after: writer rewrite rejected (number 92)',
      trace: [
        { agent: 'Writer', action: 'rewrite', input_summary: '', output_summary: 'with a 92% rate', ms: 1500, ok: true },
        { agent: 'Verifier', action: 'check_writer', input_summary: '', output_summary: 'reject: number 92', ms: 0.8, ok: false },
        { agent: 'Editor', action: 'repair', input_summary: '', output_summary: 'Repaired sentence.', ms: 1400, ok: true },
      ],
    });
    render(<InsightLog rows={[traced]} info={null} />);
    expect(screen.queryByRole('list', { name: 'Agent trace' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Show agent trace \(3 steps\)/ }));
    const list = screen.getByRole('list', { name: 'Agent trace' });
    const steps = within(list).getAllByRole('listitem');
    expect(steps).toHaveLength(3);
    expect(steps[1]!.className).toContain('trace-bad');
    expect(steps[1]!.textContent).toContain('reject: number 92');
  });
});
