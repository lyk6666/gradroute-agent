import { LoaderCircle } from 'lucide-react';

export default function Loading() {
  return (
    <main aria-busy="true" aria-live="polite" className="route-state-page">
      <span className="route-state-icon is-loading"><LoaderCircle aria-hidden="true" size={28} /></span>
      <h1>Preparing the workspace</h1>
      <p>Loading the grounded interface and its safe API boundary…</p>
    </main>
  );
}
