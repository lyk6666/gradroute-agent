import Link from 'next/link';
import { FileQuestion, House } from 'lucide-react';

export default function NotFound() {
  return (
    <main className="route-state-page">
      <span className="route-state-icon"><FileQuestion aria-hidden="true" size={28} /></span>
      <h1>Page not found</h1>
      <p>The requested prototype route does not exist.</p>
      <Link href="/"><House aria-hidden="true" size={16} /> Return to Main</Link>
    </main>
  );
}
