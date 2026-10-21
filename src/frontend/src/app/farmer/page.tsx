import { AuthGate } from '@/components/AuthGate';
import { FarmerWorkspace } from '@/components/FarmerWorkspace';
import { RoleGate } from '@/components/RoleGate';

export default function FarmerPage() {
  return <AuthGate><RoleGate allowedRoles={['FARMER', 'PLATFORM_ADMIN']}><FarmerWorkspace /></RoleGate></AuthGate>;
}
