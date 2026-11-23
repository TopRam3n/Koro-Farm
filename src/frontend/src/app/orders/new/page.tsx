import { AuthGate } from '@/components/AuthGate';
import { NewOrderForm } from '@/components/trade/OrdersWorkspace';
export default function Page() { return <AuthGate><NewOrderForm /></AuthGate>; }
