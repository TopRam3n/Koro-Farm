import { AuthGate } from '@/components/AuthGate';
import { FulfilmentOverview } from '@/components/trade/FulfilmentOverview';

// R1 WP5 (M1): the consolidated, role-aware queue view replaces the earlier single-order read-only summary
// (ModuleWorkspace kind "fulfilment", which is kept for the other workspace views that share it).
export default function Page() { return <AuthGate><FulfilmentOverview /></AuthGate>; }
