const labels = {
  real: 'Real NTU/CCDS',
  simulated: 'Simulated',
  derived: 'Derived',
  injected: 'Scenario-injected',
} as const;

export type ProvenanceKind = keyof typeof labels;

export function ProvenanceBadge({ kind }: { kind: ProvenanceKind }) {
  return <span className={`provenance-badge provenance-${kind}`}>{labels[kind]}</span>;
}
