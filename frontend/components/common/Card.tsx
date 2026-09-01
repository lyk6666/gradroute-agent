import type { ElementType, ReactNode } from 'react';

type CardProps = {
  action?: ReactNode;
  as?: ElementType;
  children: ReactNode;
  className?: string;
  eyebrow?: string;
  title?: string;
};

export function Card({
  action,
  as: Component = 'section',
  children,
  className = '',
  eyebrow,
  title,
}: CardProps) {
  return (
    <Component className={`card ${className}`.trim()}>
      {title || eyebrow || action ? (
        <header className="card-header">
          <div>
            {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
            {title ? <h2>{title}</h2> : null}
          </div>
          {action}
        </header>
      ) : null}
      {children}
    </Component>
  );
}
