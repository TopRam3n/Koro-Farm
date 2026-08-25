import { CheckCircle2, Package, ShieldCheck, Users } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Allocation, SupplyMetrics } from '@/lib/mockdata';

interface SupplyOverviewProps {
  metrics: SupplyMetrics;
  allocations: Allocation[];
}

export function SupplyOverview({ metrics, allocations }: SupplyOverviewProps) {
  const coverage = Math.round((metrics.committedKg / metrics.requiredKg) * 100);

  return (
    <Card className="overflow-hidden border-primary/20 bg-card/90">
      <CardHeader className="border-b border-border/60 pb-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-primary">Requirement REQ-HOTEL-001</p>
            <CardTitle className="mt-2 text-2xl">500 kg Grade A ginger</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">Blue Mountain Lodge · Montego Bay · 01-02 Sep 2026</p>
          </div>
          <Badge className="bg-success/10 text-success hover:bg-success/10">
            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
            SLA preserved
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-6 pt-6 md:grid-cols-[1fr_0.8fr]">
        <div>
          <div className="mb-2 flex items-end justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Committed supply</p>
              <p className="font-mono text-4xl font-semibold tracking-tight">{metrics.committedKg}<span className="ml-1 text-lg text-muted-foreground">kg</span></p>
            </div>
            <p className="font-mono text-sm text-success">{coverage}% covered</p>
          </div>
          <div className="h-3 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-success transition-all" style={{ width: `${coverage}%` }} />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div className="border-l-2 border-primary pl-3"><p className="text-muted-foreground">Required</p><p className="font-semibold">{metrics.requiredKg} kg</p></div>
            <div className="border-l-2 border-warning pl-3"><p className="text-muted-foreground">Standby reserve</p><p className="font-semibold">{metrics.standbyKg} kg</p></div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Stat icon={Users} label="Committed farmers" value={metrics.committedFarmerCount} />
          <Stat icon={ShieldCheck} label="Reserve farmers" value={metrics.standbyFarmerCount} />
          <Stat icon={Package} label="Current shortfall" value={`${metrics.shortfallKg} kg`} />
          <Stat icon={CheckCircle2} label="Supply health" value={metrics.health} success />
        </div>
      </CardContent>
      <div className="border-t border-border/60 bg-muted/20 px-6 py-3 text-xs text-muted-foreground">
        {allocations.length} traceable production lots across {metrics.committedFarmerCount + metrics.standbyFarmerCount} farmers
      </div>
    </Card>
  );
}

function Stat({ icon: Icon, label, value, success = false }: { icon: typeof Users; label: string; value: string | number; success?: boolean }) {
  return <div className="rounded-md border border-border/70 bg-background/60 p-3"><Icon className={`mb-2 h-4 w-4 ${success ? 'text-success' : 'text-primary'}`} /><p className="text-xs text-muted-foreground">{label}</p><p className={`mt-1 font-mono text-sm font-semibold ${success ? 'text-success' : ''}`}>{value}</p></div>;
}