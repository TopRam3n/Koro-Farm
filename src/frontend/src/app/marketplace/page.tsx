import { AuthGate } from '@/components/AuthGate';
import { MarketplaceWorkspace } from '@/components/MarketplaceWorkspace';
import { RoleGate } from '@/components/RoleGate';

export default function MarketplacePage() {
  return <AuthGate><RoleGate allowedRoles={['BUYER', 'PLATFORM_ADMIN']}><MarketplaceWorkspace /></RoleGate></AuthGate>;
}
