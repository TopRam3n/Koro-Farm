import type { Metadata } from 'next';
import { Providers } from './providers';
import './globals.css';

export const metadata: Metadata = {
  title: 'KoroFarm | Supply Assurance',
  description: 'Caribbean agricultural supply assurance and execution layer',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><Providers>{children}</Providers></body></html>;
}
