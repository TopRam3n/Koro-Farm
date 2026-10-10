import Index from '@/views/Index';
import { AuthGate } from '@/components/AuthGate';

export default function Page() {
  return <AuthGate><Index /></AuthGate>;
}