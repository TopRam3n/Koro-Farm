'use client';

import Link from 'next/link';
import { MailCheck, Sprout } from 'lucide-react';

export default function Signup() {
  return <div className="flex min-h-screen items-center justify-center bg-background p-4 sm:p-8"><div className="w-full max-w-md rounded-[14px] border border-white/[0.08] bg-card p-8 text-center sm:p-10"><div className="flex items-center justify-center gap-2"><span className="rounded-xl bg-primary/10 p-2"><Sprout className="h-6 w-6 text-primary" /></span><strong className="text-xl">KoroFarm</strong></div><MailCheck className="mx-auto mt-8 h-6 w-6 text-primary" /><h1 className="mt-4 text-2xl font-bold">Invitation required</h1><p className="mt-3 text-sm leading-6 text-muted-foreground">KoroFarm pilot accounts are provisioned by an organization administrator. Use the invitation sent to your approved email address.</p><p className="mt-8 text-sm text-muted-foreground">Already invited? <Link href="/login" className="font-medium text-primary hover:underline">Sign in</Link></p></div></div>;
}
