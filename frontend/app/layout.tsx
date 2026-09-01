import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'Graduation Exception Agent',
    template: '%s | Graduation Exception Agent',
  },
  description:
    'Team AIGO prototype for transparent, grounded NTU CCDS graduation exception resolution.',
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
