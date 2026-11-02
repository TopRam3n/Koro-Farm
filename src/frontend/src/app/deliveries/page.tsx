import { AuthGate } from '@/components/AuthGate';
import { BuyerDeliveries } from '@/components/trade/BuyerDeliveries';
import { RoleGate } from '@/components/RoleGate';

export default function Page() {
  return <AuthGate><RoleGate allowedRoles={['BUYER', 'PLATFORM_ADMIN']}><BuyerDeliveries /></RoleGate></AuthGate>;
}
