import { ControlCenterView } from '@/components/ControlCenterView';
import { AuthGate } from '@/components/AuthGate';

export default function Page() {
  return <AuthGate><ControlCenterView /></AuthGate>;
}
