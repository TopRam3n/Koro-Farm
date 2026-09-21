import { AuthGate } from '@/components/AuthGate'; import { ModuleWorkspace } from '@/components/ModuleWorkspace';
export default async function Page({params}:{params:Promise<{id:string}>}){ const {id}=await params; return <AuthGate><ModuleWorkspace kind="programme" entityId={id} /></AuthGate>; }
