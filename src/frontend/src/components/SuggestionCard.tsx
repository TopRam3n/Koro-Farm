import { cn } from '@/lib/utils';
import { Suggestion } from '@/lib/mockdata';
import { Lightbulb, AlertTriangle, TrendingUp, ArrowRight, Zap } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CSSProperties } from 'react';

interface SuggestionCardProps {
  suggestion: Suggestion;
  className?: string;
  style?: CSSProperties;
}

const typeConfig = {
  optimization: {
    icon: Lightbulb,
    iconClassName: 'text-success bg-success/10',
    label: 'Optimization',
  },
  warning: {
    icon: AlertTriangle,
    iconClassName: 'text-warning bg-warning/10',
    label: 'Warning',
  },
  insight: {
    icon: TrendingUp,
    iconClassName: 'text-primary bg-primary/10',
    label: 'Insight',
  },
};

const priorityConfig = {
  high: 'bg-destructive/10 text-destructive border-destructive/20',
  medium: 'bg-warning/10 text-warning border-warning/20',
  low: 'bg-muted text-muted-foreground border-muted',
};

export function SuggestionCard({ suggestion, className, style }: SuggestionCardProps) {
  const type = typeConfig[suggestion.type];
  const Icon = type.icon;

  return (
    <div 
      className={cn(
        'glass-card rounded-xl p-4 transition-all duration-300 hover:shadow-xl animate-slide-up',
        className
      )}
      style={style}
    >
      <div className="flex gap-4">
        <div className={cn('p-2.5 rounded-xl shrink-0 h-fit', type.iconClassName)}>
          <Icon className="h-5 w-5" />
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2 mb-2">
            <h3 className="font-semibold text-foreground leading-tight">
              {suggestion.title}
            </h3>
            <Badge variant="outline" className={cn('text-xs shrink-0', priorityConfig[suggestion.priority])}>
              {suggestion.priority}
            </Badge>
          </div>
          
          <p className="text-sm text-muted-foreground mb-3 leading-relaxed">
            {suggestion.description}
          </p>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {suggestion.potentialSavings && (
                <div className="flex items-center gap-1.5 text-success">
                  <Zap className="h-4 w-4" />
                  <span className="text-sm font-medium">{suggestion.potentialSavings}</span>
                </div>
              )}
              <div className="flex gap-1">
                {suggestion.affectedRooms.slice(0, 2).map(room => (
                  <Badge key={room} variant="secondary" className="text-xs">
                    {room}
                  </Badge>
                ))}
                {suggestion.affectedRooms.length > 2 && (
                  <Badge variant="secondary" className="text-xs">
                    +{suggestion.affectedRooms.length - 2}
                  </Badge>
                )}
              </div>
            </div>
            
            <Button variant="ghost" size="sm" className="text-primary hover:text-primary/80">
              Apply
              <ArrowRight className="h-4 w-4 ml-1" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
