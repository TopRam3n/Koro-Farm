import { AuthGate } from '@/components/AuthGate';
import { ExceptionsWorkspace } from '@/components/trade/ExceptionsWorkspace';
export default function Page() { return <AuthGate><ExceptionsWorkspace /></AuthGate>; }
