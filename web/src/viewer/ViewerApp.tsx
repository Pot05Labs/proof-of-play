import { useCallback, useState } from 'react';
import { JoinScreen } from './JoinScreen';
import { LiveScreen } from './LiveScreen';
import { clearSession, loadSession, saveSession, type ViewerSession } from './session';

export default function ViewerApp() {
  const [session, setSession] = useState<ViewerSession | null>(() => loadSession());
  const [lostNotice, setLostNotice] = useState(false);

  const onJoined = useCallback((s: ViewerSession) => {
    saveSession(s);
    setLostNotice(false);
    setSession(s);
  }, []);

  const onLost = useCallback(() => {
    clearSession();
    setSession(null);
    setLostNotice(true);
  }, []);

  const onUpdate = useCallback((s: ViewerSession) => {
    saveSession(s);
    setSession(s);
  }, []);

  if (!session) return <JoinScreen onJoined={onJoined} sessionLost={lostNotice} />;
  return <LiveScreen session={session} onSessionLost={onLost} onUpdate={onUpdate} />;
}
