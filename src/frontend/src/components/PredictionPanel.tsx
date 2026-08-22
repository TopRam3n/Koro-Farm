import { TrendingUp, Clock, AlertCircle, CheckCircle2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

interface Prediction {
  time: string;
  occupancy: number;
  energy: number;
  confidence: number;
}

const predictions: Prediction[] = [
  { time: '2:00 PM', occupancy: 78, energy: 82, confidence: 94 },
  { time: '3:00 PM', occupancy: 65, energy: 70, confidence: 91 },
  { time: '4:00 PM', occupancy: 52, energy: 58, confidence: 88 },
  { time: '5:00 PM', occupancy: 35, energy: 42, confidence: 85 },
];

export function PredictionPanel() {
  return (
    <div className="glass-card rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-primary/10">
            <TrendingUp className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h3 className="font-semibold text-foreground">ML Predictions</h3>
            <p className="text-xs text-muted-foreground">Next 4 hours forecast</p>
          </div>
        </div>
        <Badge variant="outline" className="bg-success/10 text-success border-success/20">
          <CheckCircle2 className="h-3 w-3 mr-1" />
          Model Active
        </Badge>
      </div>

      <div className="space-y-3">
        {predictions.map((pred, index) => (
          <div 
            key={pred.time}
            className="flex items-center justify-between p-3 rounded-lg bg-muted/50 hover:bg-muted transition-colors"
            style={{ animationDelay: `${index * 100}ms` }}
          >
            <div className="flex items-center gap-3">
              <Clock className="h-4 w-4 text-muted-foreground" />
              <span className="font-medium text-sm">{pred.time}</span>
            </div>
            
            <div className="flex items-center gap-4">
              <div className="text-right">
                <span className="text-xs text-muted-foreground block">Occupancy</span>
                <span className="text-sm font-semibold">{pred.occupancy}%</span>
              </div>
              <div className="text-right">
                <span className="text-xs text-muted-foreground block">Energy</span>
                <span className="text-sm font-semibold text-energy">{pred.energy}%</span>
              </div>
              <div className="w-16">
                <div className="flex items-center justify-end gap-1">
                  <div 
                    className="h-1.5 rounded-full bg-success" 
                    style={{ width: `${pred.confidence}%` }}
                  />
                </div>
                <span className="text-xs text-muted-foreground">{pred.confidence}% conf.</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 p-3 rounded-lg border border-warning/20 bg-warning/5">
        <div className="flex items-start gap-2">
          <AlertCircle className="h-4 w-4 text-warning shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-foreground">Peak Alert</p>
            <p className="text-xs text-muted-foreground">
              High occupancy expected at 2:00 PM. Consider pre-cooling Science Building.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
