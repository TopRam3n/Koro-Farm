import { AuthGate } from '@/components/AuthGate';
import { ProgrammesWorkspace } from '@/components/ProgrammesWorkspace';

export default function Page() {
  return <AuthGate><ProgrammesWorkspace /></AuthGate>;
}
