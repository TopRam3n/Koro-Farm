import { AuthGate } from '@/components/AuthGate';
import { BuyerPortal } from '@/components/trade/BuyerPortal';
import { RoleGate } from '@/components/RoleGate';

export default function Page() {
  return <AuthGate><RoleGate allowedRoles={['BUYER', 'PLATFORM_ADMIN']}><BuyerPortal /></RoleGate></AuthGate>;
}
