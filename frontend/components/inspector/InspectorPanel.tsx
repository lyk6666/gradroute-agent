import type { ReactNode } from 'react';

export function InspectorPanel({
  children,
  subtitle,
  title,
}: {
  children: ReactNode;
  subtitle?: string;
  title: string;
}) {
  return (
    <aside className="card inspector-panel" aria-label={title}>
      <header className="inspector-heading">
        <span className="inspector-spark" aria-hidden="true">✦</span>
        <div>
          <h2>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
      </header>
      {children}
    </aside>
  );
}

export function InspectorSection({ children, title }: { children: ReactNode; title: string }) {
  return (
    <section className="inspector-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}
