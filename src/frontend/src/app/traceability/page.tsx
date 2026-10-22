import { AuthGate } from '@/components/AuthGate';
import { OperationalViews } from '@/components/OperationalViews';
export default function Page() { return <AuthGate><OperationalViews kind="traceability" /></AuthGate>; }
