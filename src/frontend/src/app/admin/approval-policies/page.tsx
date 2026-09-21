import { AuthGate } from '@/components/AuthGate'; import { GovernanceWorkspace } from '@/components/GovernanceWorkspace';
export default function Page(){ return <AuthGate><GovernanceWorkspace kind="policies" /></AuthGate>; }
