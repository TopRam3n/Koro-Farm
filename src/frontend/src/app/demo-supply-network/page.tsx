import { AuthGate } from '@/components/AuthGate';
import { AppShell } from '@/components/AppShell';
import { DemoSupplyNetwork } from '@/components/DemoSupplyNetwork';

export default function Page() {
  return <AuthGate><AppShell programme="Demo Supply Network"><main className="mx-auto max-w-6xl px-4 py-8 sm:px-6"><h1 className="mb-6 text-3xl font-semibold">Demo Supply Network</h1><DemoSupplyNetwork /></main></AppShell></AuthGate>;
}
