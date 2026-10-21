import { AuthGate } from '@/components/AuthGate';
import { IntelligenceLab } from '@/components/IntelligenceLab';

export default function Page() {
  return <AuthGate><IntelligenceLab /></AuthGate>;
}
