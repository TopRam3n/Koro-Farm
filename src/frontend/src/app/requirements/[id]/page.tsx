import { AuthGate } from '@/components/AuthGate'; import Index from '@/pages/Index';
export default function Page(){ return <AuthGate><Index /></AuthGate>; }
