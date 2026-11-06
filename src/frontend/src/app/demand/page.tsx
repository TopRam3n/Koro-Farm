import { AuthGate } from '@/components/AuthGate';
import { DemandWorkspace } from '@/components/DemandWorkspace';

export default function Page() {
  return <AuthGate><DemandWorkspace /></AuthGate>;
}
