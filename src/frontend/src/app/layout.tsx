import type { Metadata } from 'next';
import { Providers } from './providers';
import './globals.css';

export const metadata: Metadata = {
  title: 'KoroFarm | Agricultural Intelligence & Coordination',
  description: 'Agricultural intelligence and coordination infrastructure for the Caribbean. Understand production. Anticipate risk. Coordinate action.',
  icons: {
    icon: '/brand/korofarm-mark.png',
    shortcut: '/brand/korofarm-mark.png',
    apple: '/brand/korofarm-mark.png',
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" suppressHydrationWarning><body><Providers>{children}</Providers></body></html>;
}
