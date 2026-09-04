import Link from 'next/link';

export type AppSection = 'main' | 'data' | 'evaluation';

type TopNavigationProps = {
  activeSection: AppSection;
  preview?: boolean;
  systemStatus?: 'checking' | 'operational' | 'offline';
};

const links: Array<{ href: string; label: string; section: AppSection }> = [
  { href: '/', label: 'Main', section: 'main' },
  { href: '/data', label: 'Data', section: 'data' },
  { href: '/evaluation', label: 'Evaluation', section: 'evaluation' },
];

export function TopNavigation({ activeSection, preview = false, systemStatus }: TopNavigationProps) {
  const status = systemStatus ?? (preview ? 'checking' : 'operational');
  const statusLabel = {
    checking: 'Connecting',
    operational: 'Operational',
    offline: 'Runtime offline',
  }[status];
  return (
    <header className="topbar">
      <div className="brand-lockup">
        <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
        <span>
          <strong>Graduation Exception Agent</strong>
          <small>NTU CCDS-grounded prototype</small>
        </span>
      </div>

      <nav className="topnav" aria-label="Primary navigation">
        {links.map((link) => (
          <Link
            aria-current={activeSection === link.section ? 'page' : undefined}
            className={activeSection === link.section ? 'is-active' : undefined}
            data-demo-target={`nav-${link.section}`}
            href={link.href}
            key={link.section}
          >
            {link.label}
          </Link>
        ))}
      </nav>

      <div className="topbar-actions">
        <span className="event-badge">✦ IGNITE: SimplifyNext Agentic AI Hackathon 2026 Prototype</span>
        <span aria-live="polite" className={`system-health is-${status}`} role="status">
          <i /> {statusLabel}
        </span>
        <span className="team-badge" title="Team Leader Li Yikai; Tang Ruixuan; Ong Alvin; Goh Hym Leong">
          <b>A</b>
          <span className="team-details">
            <strong>Team AIGO</strong>
            <small><em>Team Leader</em> Li Yikai · Tang Ruixuan · Ong Alvin · Goh Hym Leong</small>
          </span>
        </span>
      </div>
    </header>
  );
}
