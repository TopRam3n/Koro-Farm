'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { Zap, Loader2 } from 'lucide-react';
import { resolvePostLoginRoute } from '@/features/identity/auth/routing';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const router = useRouter();
  const { toast } = useToast();
  const { signIn } = useAuth();
  const [workspace, setWorkspace] = useState<'AUTO' | 'FARMER' | 'BUYER'>('AUTO');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      // Read the authoritative membership projection after sign-in rather than signup UX storage.
      let snapshot = await signIn(email, password);
      if (!snapshot.memberships.length) {
        const { supabase } = await import('@/integrations/supabase/client');
        const { error: claimError } = await supabase.rpc('claim_signup_membership');
        if (!claimError) {
          const { createAuthAdapter } = await import('@/features/identity/auth');
          snapshot = await createAuthAdapter().getSnapshot();
        }
      }

      toast({
        title: "Welcome back!",
        description: "Successfully logged in.",
      });
      const requested = workspace === 'AUTO' ? null : snapshot.memberships.find(m => m.status === 'ACTIVE' && m.persona === workspace);
      if (workspace !== 'AUTO' && !requested) {
        toast({ title: `${workspace === 'FARMER' ? 'Farmer' : 'Buyer'} dashboard unavailable`, description: `This account does not have an active ${workspace.toLowerCase()} membership.`, variant: 'destructive' });
        return;
      }
      router.push(requested ? (workspace === 'FARMER' ? '/f' : '/b') : resolvePostLoginRoute(snapshot.memberships));
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
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="glass-card rounded-2xl p-8 space-y-6">
          {/* Logo */}
          <div className="text-center space-y-2">
            <div className="flex items-center justify-center gap-2 mb-4">
              <div className="p-2 rounded-xl bg-primary/10">
                <Zap className="h-6 w-6 text-primary" />
              </div>
              <span className="text-xl font-bold text-foreground">Koro Farm</span>
            </div>
            <h1 className="text-2xl font-bold text-foreground">Welcome back</h1>
            <p className="text-muted-foreground">Sign in to access the dashboard</p>
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
              <Label>Open after sign in</Label>
              <div className="grid grid-cols-3 gap-2">
                {([['AUTO', 'My workspace'], ['FARMER', 'Farmer'], ['BUYER', 'Buyer']] as const).map(([value, label]) => (
                  <Button key={value} type="button" variant={workspace === value ? 'default' : 'outline'} onClick={() => setWorkspace(value)}>{label}</Button>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">Dashboard access is based on your active Supabase membership.</p>
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

          {/* Footer */}
          <p className="text-center text-sm text-muted-foreground">
            Don't have an account?{' '}
            <Link href="/signup" className="text-primary hover:underline font-medium">
              Sign up
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
