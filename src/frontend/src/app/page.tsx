import { AuthGate } from '@/components/AuthGate';
import Landing from '@/components/Landing';
import { RoleHome } from '@/components/RoleHome';

export default function Page() {
  return <><Landing /><AuthGate><RoleHome /></AuthGate></>;
}
