import { ArrowLeft, Sprout } from 'lucide-react';
import Link from 'next/link';

export function SubpageShell({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children: React.ReactNode }) {
  return <div className="min-h-screen bg-background"><header className="border-b border-white/[0.07] bg-background/90 px-5 py-4 backdrop-blur"><div className="mx-auto flex max-w-5xl items-center justify-between"><Link href="/" className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-white/[0.04] hover:text-foreground"><ArrowLeft className="h-4 w-4" />Control room</Link><div className="flex items-center gap-2 text-sm font-semibold"><Sprout className="h-4 w-4 text-primary" />KoroFarm</div></div></header><main className="mx-auto max-w-5xl px-5 py-8 sm:py-12"><header className="mb-8 border-b border-white/[0.07] pb-7"><p className="section-eyebrow">{eyebrow}</p><h1 className="mt-2 text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">{title}</h1><p className="mt-2 text-sm text-muted-foreground">{description}</p></header>{children}</main></div>;
}
