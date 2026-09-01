import Link from 'next/link';

export type AppSection = 'main' | 'data' | 'evaluation';

type TopNavigationProps = {
  activeSection: AppSection;
};

const links: Array<{ href: string; label: string; section: AppSection }> = [
  { href: '/', label: 'Main', section: 'main' },
  { href: '/data', label: 'Data', section: 'data' },
  { href: '/evaluation', label: 'Evaluation', section: 'evaluation' },
];

export function TopNavigation({ activeSection }: TopNavigationProps) {
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
            href={link.href}
            key={link.section}
          >
            {link.label}
          </Link>
        ))}
      </nav>

      <div className="topbar-actions">
        <span className="event-badge">✦ IGNITE 2026 Prototype</span>
        <span className="system-health"><i /> Interface ready</span>
        <span className="team-badge"><b>A</b> Team AIGO</span>
      </div>
    </header>
  );
}
