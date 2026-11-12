import { AuthGate } from '@/components/AuthGate';
import { OrdersWorkspace } from '@/components/trade/OrdersWorkspace';
export default function Page() { return <AuthGate><OrdersWorkspace /></AuthGate>; }
