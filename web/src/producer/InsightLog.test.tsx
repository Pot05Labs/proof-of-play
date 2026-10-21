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
});
