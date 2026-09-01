import type { ReactNode } from 'react';
import { TopNavigation, type AppSection } from './TopNavigation';

type AppShellProps = {
  activeSection: AppSection;
  children: ReactNode;
};

export function AppShell({ activeSection, children }: AppShellProps) {
  return (
    <div className="app-shell">
      <TopNavigation activeSection={activeSection} />
      <main className="page-content">{children}</main>
      <footer className="prototype-footer">
        <span>Team AIGO · SimplifyNext IGNITE 2026</span>
        <span>Research prototype · Not an official NTU service</span>
      </footer>
    </div>
  );
}
