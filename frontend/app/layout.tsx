import type { Metadata, Viewport } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'Graduation Exception Agent',
    template: '%s | Graduation Exception Agent',
  },
  description:
    'Team AIGO prototype for transparent, grounded NTU CCDS graduation exception resolution.',
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
