import type { ReactNode } from 'react';
import { TopNavigation, type AppSection } from './TopNavigation';

type AppShellProps = {
  activeSection: AppSection;
  children: ReactNode;
  systemStatus?: 'checking' | 'operational' | 'offline';
  workspace?: boolean;
};

export function AppShell({ activeSection, children, systemStatus, workspace = false }: AppShellProps) {
  return (
    <div className={`app-shell${workspace ? ' app-shell-workspace' : ''}`}>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <TopNavigation activeSection={activeSection} preview={workspace} systemStatus={systemStatus} />
      <main className={`page-content${workspace ? ' page-content-workspace' : ''}`} id="main-content" tabIndex={-1}>
        {children}
      </main>
      {!workspace ? (
        <footer className="prototype-footer">
          <span>Team AIGO · SimplifyNext IGNITE 2026</span>
          <span>Research prototype · Not an official NTU service</span>
        </footer>
      ) : null}
    </div>
  );
}
