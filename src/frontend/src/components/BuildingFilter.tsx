import { cn } from '@/lib/utils';
import { buildings } from '@/lib/mockdata';
import { Building2 } from 'lucide-react';

interface BuildingFilterProps {
  selected: string | null;
  onSelect: (building: string | null) => void;
}

export function BuildingFilter({ selected, onSelect }: BuildingFilterProps) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <button
        onClick={() => onSelect(null)}
        className={cn(
          'px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200',
          'flex items-center gap-2',
          selected === null
            ? 'bg-primary text-primary-foreground shadow-glow'
            : 'bg-card text-muted-foreground hover:bg-accent hover:text-accent-foreground border border-border'
        )}
      >
        <Building2 className="h-4 w-4" />
        All Buildings
      </button>
      {buildings.map((building) => (
        <button
          key={building}
          onClick={() => onSelect(building)}
          className={cn(
            'px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200',
            selected === building
              ? 'bg-primary text-primary-foreground shadow-glow'
              : 'bg-card text-muted-foreground hover:bg-accent hover:text-accent-foreground border border-border'
          )}
        >
          {building}
        </button>
      ))}
    </div>
  );
}
