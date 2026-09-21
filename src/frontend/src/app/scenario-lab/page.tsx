import { AuthGate } from '@/components/AuthGate'; import { ScenarioLab } from '@/components/ScenarioLab';
export default function Page(){ return <AuthGate><ScenarioLab /></AuthGate>; }
