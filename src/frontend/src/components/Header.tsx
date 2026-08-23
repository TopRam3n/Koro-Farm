'use client';

import { Bell, CircleDot, Moon, RefreshCw, Sprout, Sun, UserRound } from 'lucide-react';
import Link from 'next/link';
import { useTheme } from 'next-themes';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useState, useEffect } from 'react';

export function Header() {
  const [currentTime, setCurrentTime] = useState(new Date());
  const { resolvedTheme, setTheme } = useTheme();

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="sticky top-0 z-50 border-b border-border/70 bg-background/90 px-6 py-4 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1500px] items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="rounded-md bg-primary p-2 text-primary-foreground">
              <Sprout className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-foreground">Koro<span className="text-primary">Farm</span></h1>
              <p className="text-xs text-muted-foreground">Supply assurance control room</p>
            </div>
          </div>
          <Badge variant="outline" className="ml-4 border-primary/30 bg-primary/5 text-primary">
            <CircleDot className="mr-2 h-3 w-3" />
            Demo programme
          </Badge>
        </div>

        <div className="flex items-center gap-6">
          <div className="text-right">
            <p className="text-sm font-medium text-foreground font-mono">
              {currentTime.toLocaleTimeString('en-US', {
                hour: '2-digit', 
                minute: '2-digit',
                second: '2-digit',
                hour12: true
              })}
            </p>
            <p className="text-xs text-muted-foreground">
              {currentTime.toLocaleDateString('en-US', { 
                weekday: 'long',
                month: 'short',
                day: 'numeric' 
              })}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button asChild variant="ghost" size="icon" className="relative" aria-label="View notifications">
              <Link href="/notifications">
                <Bell className="h-5 w-5 text-muted-foreground" />
              <span className="absolute top-1 right-1 w-2 h-2 bg-destructive rounded-full" />
              </Link>
            </Button>
            <Button variant="ghost" size="icon" aria-label="Refresh dashboard">
              <RefreshCw className="h-5 w-5 text-muted-foreground" />
            </Button>
            <Button variant="ghost" size="icon" aria-label="Toggle light and dark mode" onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}>
              {resolvedTheme === 'dark' ? <Sun className="h-5 w-5 text-muted-foreground" /> : <Moon className="h-5 w-5 text-muted-foreground" />}
            </Button>
            <Button asChild variant="ghost" size="icon" aria-label="View profile">
              <Link href="/profile"><UserRound className="h-5 w-5 text-muted-foreground" /></Link>
            </Button>
          </div>
        </div>
      </div>
    </header>
  );
}
