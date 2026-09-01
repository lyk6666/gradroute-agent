import type { Metadata } from 'next';
import { EvaluationDashboard } from '@/features/evaluation-dashboard/EvaluationDashboard';

export const metadata: Metadata = {
  title: 'Evaluation Evidence',
  description: 'Inspect accepted Stage 7 fixture and Bedrock evaluation evidence.',
};

export default function EvaluationPage() {
  return <EvaluationDashboard />;
}
