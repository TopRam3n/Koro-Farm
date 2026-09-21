import { AuthGate } from '@/components/AuthGate'; import { ModuleWorkspace } from '@/components/ModuleWorkspace';
export default function Page(){ return <AuthGate><ModuleWorkspace kind="activity" /></AuthGate>; }
