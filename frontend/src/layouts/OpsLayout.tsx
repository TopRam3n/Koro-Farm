import Link from 'next/link';
import { PersonaGuard } from '@/components/auth/PersonaGuard';

export function OpsLayout({ children }: { children: React.ReactNode }) {
    return <PersonaGuard persona="OPS"><div className="min-h-screen bg-background"><header className="border-b px-5 py-4"><div className="mx-auto flex max-w-6xl items-center justify-between"><Link href="/ops" className="font-semibold">KoroFarm · Operations</Link><span className="text-xs text-warning">Escalation triage</span></div></header><main className="mx-auto max-w-6xl p-5">{children}</main></div></PersonaGuard>;
}
