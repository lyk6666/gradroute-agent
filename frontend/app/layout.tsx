import type { Metadata, Viewport } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'Graduation Exception Agent',
    template: '%s | Graduation Exception Agent',
  },
  description:
    'Team AIGO prototype for transparent, explainable resolution of graduation-critical academic and course-registration cases, grounded in NTU CCDS reference data.',
};

export const viewport: Viewport = {
  colorScheme: 'light',
  themeColor: '#111827',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
