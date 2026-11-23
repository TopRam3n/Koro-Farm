import { AuthGate } from '@/components/AuthGate';
import { SuppliersWorkspace } from '@/components/trade/SuppliersWorkspace';
export default function Page() { return <AuthGate><SuppliersWorkspace /></AuthGate>; }
