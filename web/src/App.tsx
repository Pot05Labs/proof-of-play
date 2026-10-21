import { lazy, Suspense } from 'react';

const ViewerApp = lazy(() => import('./viewer/ViewerApp'));
const ProducerApp = lazy(() => import('./producer/ProducerApp'));

export function isProducerPath(pathname: string): boolean {
  return /^\/producer\/?$/.test(pathname);
}

export function App() {
  const producer = isProducerPath(window.location.pathname);
  return (
    <Suspense fallback={<p className="sr-only">Loading</p>}>
      {producer ? <ProducerApp /> : <ViewerApp />}
    </Suspense>
  );
}
