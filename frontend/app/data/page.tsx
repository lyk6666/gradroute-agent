import type { Metadata } from 'next';
import { DataExplorer } from '@/features/data-explorer/DataExplorer';

export const metadata: Metadata = {
  title: 'Grounded Data',
  description: 'Inspect processed NTU CCDS grounding and simulated case records.',
};

export default function DataPage() {
  return <DataExplorer />;
}
