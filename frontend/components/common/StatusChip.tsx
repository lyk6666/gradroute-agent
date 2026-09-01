import type { ReactNode } from 'react';

export type StatusTone =
  | 'active'
  | 'success'
  | 'waiting'
  | 'danger'
  | 'replan'
  | 'neutral'
  | 'ready'
  | 'escalated';

type StatusChipProps = {
  children: ReactNode;
  compact?: boolean;
  tone: StatusTone;
};

export function StatusChip({ children, compact = false, tone }: StatusChipProps) {
  return (
    <span className={`status-chip status-${tone}${compact ? ' is-compact' : ''}`}>
      {children}
    </span>
  );
}
