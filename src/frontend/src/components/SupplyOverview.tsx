import { CheckCircle2, Package, ShieldCheck, Users } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Allocation, SupplyMetrics } from '@/lib/mockdata';

interface SupplyOverviewProps {
  metrics: SupplyMetrics;
  allocations: Allocation[];
  requirementId: string;
  crop: string;
  grade: string;
  buyerName: string;
  destination: string;
  deliveryWindow: string;
}

export function SupplyOverview({ metrics, allocations, requirementId, crop, grade, buyerName, destination, deliveryWindow }: SupplyOverviewProps) {
  const coverage = Math.round((metrics.committedKg / metrics.requiredKg) * 100);
  const covered = metrics.health === 'COVERED';

  return (
    <Card className="overflow-hidden border-primary/20 bg-card/90">
      <CardHeader className="border-b border-border/60 pb-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-primary">Requirement {requirementId}</p>
            <CardTitle className="mt-2 text-2xl">{metrics.requiredKg} kg Grade {grade} {crop.toLowerCase()}</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">{buyerName} · {destination} · {deliveryWindow}</p>
          </div>
          <Badge data-testid="supply-health" className={covered ? 'bg-success/10 text-success hover:bg-success/10' : 'bg-warning/10 text-warning hover:bg-warning/10'}>
            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
            {covered ? 'SLA preserved' : metrics.health.replace(/_/g, ' ')}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-6 pt-6 md:grid-cols-[1fr_0.8fr]">
        <div>
          <div className="mb-2 flex items-end justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Committed supply</p>
              <p data-testid="committed-kg" className="font-mono text-4xl font-semibold tracking-tight">{metrics.committedKg}<span className="ml-1 text-lg text-muted-foreground">kg</span></p>
            </div>
            <p className="font-mono text-sm text-success">{coverage}% covered</p>
          </div>
          <div className="h-3 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-success transition-all" style={{ width: `${coverage}%` }} />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div className="border-l-2 border-primary pl-3"><p className="text-muted-foreground">Required</p><p className="font-semibold">{metrics.requiredKg} kg</p></div>
            <div className="border-l-2 border-warning pl-3"><p className="text-muted-foreground">Standby reserve</p><p data-testid="standby-kg" className="font-semibold">{metrics.standbyKg} kg</p></div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Stat icon={Users} label="Committed farmers" value={metrics.committedFarmerCount} />
          <Stat icon={ShieldCheck} label="Reserve farmers" value={metrics.standbyFarmerCount} />
          <Stat icon={Package} label="Current shortfall" value={`${metrics.shortfallKg} kg`} testId="shortfall-kg" />
          <Stat icon={CheckCircle2} label="Supply health" value={metrics.health} success />
        </div>
      </CardContent>
      <div className="border-t border-border/60 bg-muted/20 px-6 py-3 text-xs text-muted-foreground">
        {allocations.length} traceable production lots across {metrics.committedFarmerCount + metrics.standbyFarmerCount} farmers
      </div>
    </Card>
  );
}

function Stat({ icon: Icon, label, value, success = false, testId }: { icon: typeof Users; label: string; value: string | number; success?: boolean; testId?: string }) {
  return <div className="rounded-md border border-border/70 bg-background/60 p-3"><Icon className={`mb-2 h-4 w-4 ${success ? 'text-success' : 'text-primary'}`} /><p className="text-xs text-muted-foreground">{label}</p><p data-testid={testId} className={`mt-1 font-mono text-sm font-semibold ${success ? 'text-success' : ''}`}>{value}</p></div>;
}
