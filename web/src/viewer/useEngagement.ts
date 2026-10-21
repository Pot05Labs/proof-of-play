import { useEffect, useRef } from 'react';
import { api, ApiError } from '../lib/api';
import { createEngagement, type Engagement } from '../lib/engagement';

/** Starts the engagement reporter for one session and stops it on unmount. */
export function useEngagement(
  sessionId: string,
  tmsRef: React.MutableRefObject<number>,
  onSessionLost: () => void,
): React.MutableRefObject<Engagement | null> {
  const ref = useRef<Engagement | null>(null);
  const lost = useRef(onSessionLost);
  lost.current = onSessionLost;

  useEffect(() => {
    const eng = createEngagement({
      sessionId,
      getTms: () => tmsRef.current,
      post: (p) => api.engage(p),
      onError: (err) => {
        if (err instanceof ApiError && err.status === 404) lost.current();
      },
    });
    eng.start();
    ref.current = eng;
    return () => {
      eng.stop();
      ref.current = null;
    };
  }, [sessionId, tmsRef]);

  return ref;
}
