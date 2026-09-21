import { MyWork } from '@/components/MyWork';
import { AuthGate } from '@/components/AuthGate';

export default function Page() {
  return <AuthGate><MyWork /></AuthGate>;
}
