import { CommandCenter } from '@/components/CommandCenter';
import { AuthGate } from '@/components/AuthGate';

export default function Page() {
  return <AuthGate><CommandCenter /></AuthGate>;
}
