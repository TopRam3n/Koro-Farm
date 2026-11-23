import { AuthGate } from '@/components/AuthGate';
import { BuyersWorkspace } from '@/components/trade/BuyersWorkspace';
export default function Page() { return <AuthGate><BuyersWorkspace /></AuthGate>; }
