import type { Metadata } from 'next';
import { Providers } from './providers';
import './globals.css';

export const metadata: Metadata = {
  title: 'KoroFarm | Supply Assurance',
  description: 'Agentic Supply Assurance for Caribbean Food Systems',
  icons: {
    icon: '/brand/korofarm-mark.png',
    shortcut: '/brand/korofarm-mark.png',
    apple: '/brand/korofarm-mark.png',
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" suppressHydrationWarning><body><Providers>{children}</Providers></body></html>;
}
