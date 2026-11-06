import { AuthGate } from '@/components/AuthGate';
import { MarketplaceFulfilment } from '@/components/MarketplaceFulfilment';

export default function Page() {
  return <AuthGate><MarketplaceFulfilment /></AuthGate>;
}
