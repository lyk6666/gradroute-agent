'use client';

import { AlertTriangle, RefreshCw } from 'lucide-react';
import { useEffect } from 'react';

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error('Route render failed', error);
  }, [error]);

  return (
    <main className="route-state-page" role="alert">
      <span className="route-state-icon is-error"><AlertTriangle aria-hidden="true" size={28} /></span>
      <h1>This workspace could not be rendered</h1>
      <p>The failure is contained. Retry the route; no case action is submitted by this recovery control.</p>
      <button type="button" onClick={reset}><RefreshCw aria-hidden="true" size={16} /> Retry safely</button>
    </main>
  );
}
