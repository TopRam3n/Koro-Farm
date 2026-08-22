import { cn } from '@/lib/utils';
import { Room } from '@/lib/mockdata';
import { Users, Thermometer, Zap, Clock } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { CSSProperties } from 'react';

interface RoomCardProps {
  room: Room;
  className?: string;
  style?: CSSProperties;
}

const statusConfig = {
  active: {
    label: 'Active',
    className: 'bg-success/10 text-success border-success/20 hover:bg-success/20',
    dotClassName: 'bg-success',
  },
  idle: {
    label: 'Idle',
    className: 'bg-warning/10 text-warning border-warning/20 hover:bg-warning/20',
    dotClassName: 'bg-warning',
  },
  offline: {
    label: 'Offline',
    className: 'bg-muted text-muted-foreground border-muted hover:bg-muted',
    dotClassName: 'bg-muted-foreground',
  },
};

const typeLabels = {
  'classroom': 'Classroom',
  'lab': 'Laboratory',
  'lecture-hall': 'Lecture Hall',
  'office': 'Office',
};

export function RoomCard({ room, className, style }: RoomCardProps) {
  const status = statusConfig[room.status];
  const occupancyPercent = Math.round((room.currentOccupancy / room.capacity) * 100);

  return (
    <div 
      className={cn(
        'glass-card rounded-xl p-4 transition-all duration-300 hover:shadow-xl hover:-translate-y-0.5 animate-fade-in',
        className
      )}
      style={style}
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-semibold text-foreground">{room.name}</h3>
          <p className="text-xs text-muted-foreground">{room.id} • {typeLabels[room.type]}</p>
        </div>
        <Badge variant="outline" className={cn('text-xs', status.className)}>
          <span className={cn('w-1.5 h-1.5 rounded-full mr-1.5', status.dotClassName, room.status === 'active' && 'animate-pulse')} />
          {status.label}
        </Badge>
      </div>

      <div className="space-y-3">
        {/* Occupancy Bar */}
        <div>
          <div className="flex justify-between text-xs mb-1">
            <span className="text-muted-foreground">Occupancy</span>
            <span className="font-medium">{room.currentOccupancy}/{room.capacity}</span>
          </div>
          <div className="h-2 bg-muted rounded-full overflow-hidden">
            <div 
              className={cn(
                'h-full rounded-full transition-all duration-500',
                occupancyPercent > 80 ? 'bg-success' : 
                occupancyPercent > 40 ? 'bg-primary' : 
                occupancyPercent > 0 ? 'bg-warning' : 'bg-muted'
              )}
              style={{ width: `${occupancyPercent}%` }}
            />
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-3 gap-2 pt-2 border-t border-border/50">
          <div className="flex items-center gap-1.5 text-xs">
            <Users className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">{occupancyPercent}%</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs">
            <Zap className="h-3.5 w-3.5 text-energy" />
            <span className="text-muted-foreground">{room.energyUsage}kW</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs">
            <Thermometer className="h-3.5 w-3.5 text-primary" />
            <span className="text-muted-foreground">{room.temperature}°C</span>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between pt-2 border-t border-border/50">
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" />
            <span>{room.lastActivity}</span>
          </div>
          {room.scheduledUntil && (
            <span className="text-xs text-primary font-medium">
              Until {room.scheduledUntil}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
