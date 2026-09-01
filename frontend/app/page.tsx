import type { Metadata } from 'next';
import { MainWorkspace } from '@/features/main-workspace/MainWorkspace';

export const metadata: Metadata = {
  title: 'Case Workspace',
  description: 'Execute and inspect one grounded NTU CCDS exception case.',
};

export default function MainPage() {
  return <MainWorkspace />;
}
