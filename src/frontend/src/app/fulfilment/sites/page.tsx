import { AuthGate } from '@/components/AuthGate';
import { FulfilmentSites } from '@/components/trade/FulfilmentSites';

export default function Page() { return <AuthGate><FulfilmentSites /></AuthGate>; }
