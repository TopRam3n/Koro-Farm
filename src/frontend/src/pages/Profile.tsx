 'use client';

import { CheckCircle2, LogOut, ShieldCheck, UserRound } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/hooks/useAuth';
import { useRouter } from 'next/navigation';
import { SubpageShell } from '@/components/SubpageShell';

export default function Profile() {
	const { user, signOut } = useAuth();
	const router = useRouter();
	const displayName = user?.user_metadata?.display_name || user?.email?.split('@')[0] || 'Programme operator';

	const handleSignOut = async () => {	
		await signOut();
		router.replace('/login');
	};

	return <SubpageShell eyebrow="Account" title="Profile" description="Programme identity, access, and partner evidence settings."><div className="grid gap-6 md:grid-cols-[1.25fr_0.75fr]"><Card className="border-white/[0.08]"><CardHeader><div className="flex items-center gap-4"><div className="rounded-full bg-primary/10 p-4 text-primary"><UserRound className="h-7 w-7" /></div><div><CardTitle>{displayName}</CardTitle><p className="mt-1 text-sm text-muted-foreground">{user?.email || 'No email available'}</p></div></div></CardHeader><CardContent className="space-y-4"><div className="flex items-center justify-between border-t border-white/[0.07] pt-4"><span className="text-sm text-muted-foreground">Account role</span><Badge variant="outline">Programme operator</Badge></div><div className="flex items-center justify-between"><span className="text-sm text-muted-foreground">Operating region</span><span className="text-sm font-medium">Jamaica</span></div><div className="flex items-center justify-between"><span className="text-sm text-muted-foreground">Access status</span><span className="flex items-center gap-1.5 text-sm font-medium text-success"><CheckCircle2 className="h-4 w-4" />Active</span></div></CardContent></Card><Card className="border-white/[0.08]"><CardHeader><CardTitle className="flex items-center gap-2 text-lg"><ShieldCheck className="h-5 w-5 text-primary" />Partner evidence</CardTitle></CardHeader><CardContent><p className="text-sm leading-6 text-muted-foreground">KoroFarm records verified trade-performance evidence. It does not assess creditworthiness.</p><div className="mt-5 rounded-md border border-white/[0.08] bg-white/[0.025] p-3"><p className="text-xs text-muted-foreground">Financing</p><p className="mt-1 font-medium">NOT ASSESSED</p></div></CardContent></Card></div><Button variant="outline" className="mt-6" onClick={handleSignOut}><LogOut className="mr-2 h-4 w-4" />Sign out</Button></SubpageShell>;
}
