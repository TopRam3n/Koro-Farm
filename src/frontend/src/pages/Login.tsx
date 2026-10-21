'use client';

import { useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { supabase } from '@/integrations/supabase/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { Loader2, ShieldCheck } from 'lucide-react';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const router = useRouter();
  const { toast } = useToast();

  const handleReset = async () => {
    if (!email) {
      toast({ title: 'Email required', description: 'Enter your invited email address first.', variant: 'destructive' });
      return;
    }
    const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: `${window.location.origin}/profile` });
    toast(error
      ? { title: 'Reset unavailable', description: error.message, variant: 'destructive' }
      : { title: 'Check your email', description: 'A supported password-reset link has been requested.' });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (error) throw error;

      toast({
        title: "Welcome back!",
        description: "Successfully logged in.",
      });
      const next = new URLSearchParams(window.location.search).get('next');
      const hasAccessRequest = ['FARMER', 'BUYER'].includes(data.user?.user_metadata?.requested_access_role);
      router.push(next === '/signup' || hasAccessRequest ? '/signup' : '/');
    } catch (error) {
      toast({
        title: "Login failed",
        description: error.message || "Invalid credentials",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background grid place-items-center p-4 sm:p-8">
      <div className="grid w-full max-w-5xl overflow-hidden rounded-[14px] border border-white/[0.08] bg-card lg:grid-cols-[1.05fr_0.95fr]">
        <div className="subtle-grid hidden border-r border-white/[0.07] p-12 lg:flex lg:flex-col lg:justify-between"><div><Image src="/brand/korofarm-lockup.png" alt="KoroFarm — Supply Assurance OS" width={300} height={100} className="h-auto w-[300px] object-contain" priority /><p className="mt-20 section-eyebrow">Caribbean food systems</p><h2 className="mt-4 max-w-md text-4xl font-semibold leading-tight tracking-[-0.04em]">See the network.<br />Protect the promise.</h2><p className="mt-5 max-w-sm text-sm leading-6 text-muted-foreground">Agentic supply assurance for dependable institutional procurement.</p></div><p className="flex items-center gap-2 text-xs text-muted-foreground"><ShieldCheck className="h-4 w-4 text-primary" />Authoritative, auditable operating state</p></div>
        <div className="space-y-6 p-7 sm:p-10 lg:p-12">
          {/* Logo */}
          <div className="text-center space-y-2">
            <Image src="/brand/korofarm-wordmark.png" alt="KoroFarm — Supply Assurance OS" width={190} height={63} className="mx-auto mb-4 h-auto w-[190px] object-contain lg:hidden" priority />
            <h1 className="text-2xl font-bold text-foreground">Welcome back</h1>
            <p className="text-muted-foreground">Sign in to the supply assurance control room</p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="johndoe@gmail.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="h-11"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="h-11"
              />
            </div>

            <Button type="submit" className="w-full h-11" disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Signing in...
                </>
              ) : (
                "Sign in"
              )}
            </Button>
          </form>
          <button type="button" onClick={handleReset} className="w-full text-center text-sm font-medium text-primary hover:underline">Forgot password?</button>

          {/* Footer */}
          <p className="text-center text-sm text-muted-foreground">
            New to KoroFarm?{' '}
            <Link href="/signup" className="text-primary hover:underline font-medium">
              Create an account or request access
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
