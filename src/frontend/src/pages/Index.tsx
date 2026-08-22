import { useState } from 'react';
import Landing from "@/components/Landing";
import { Header } from '@/components/Header';
import { MetricCard } from '@/components/MetricCard';
import { RoomCard } from '@/components/RoomCard';
import { SuggestionCard } from '@/components/SuggestionCard';
import { UsageChart } from '@/components/UsageChart';
import { BuildingFilter } from '@/components/BuildingFilter';
import { PredictionPanel } from '@/components/PredictionPanel';
import { rooms, suggestions, getMetrics } from '@/lib/mockdata';
import { 
  Activity, 
  Zap, 
  Clock, 
  TrendingDown,
  LayoutGrid,
  List,
  Sparkles
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export default function Index() {
  const [selectedBuilding, setSelectedBuilding] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const metrics = getMetrics();

  const filteredRooms = selectedBuilding 
    ? rooms.filter(r => r.building === selectedBuilding)
    : rooms;

  return (
    <>
    <Landing />
    <div className="min-h-screen bg-background">
      <Header />
      
      <main className="container mx-auto px-6 py-6 max-w-[1600px]">
        {/* Metrics Row */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <MetricCard
            title="Active Rooms"
            value={metrics.activeRooms}
            subtitle={`of ${metrics.totalRooms}`}
            icon={Activity}
            variant="success"
            trend={{ value: 12, isPositive: true }}
          />
          <MetricCard
            title="Idle Rooms"
            value={metrics.idleRooms}
            subtitle="consuming energy"
            icon={Clock}
            variant="warning"
          />
          <MetricCard
            title="Current Energy"
            value={metrics.totalEnergy}
            subtitle="kWh"
            icon={Zap}
            variant="energy"
          />
          <MetricCard
            title="Potential Savings"
            value={metrics.potentialSavings}
            subtitle="kWh/hour"
            icon={TrendingDown}
            variant="success"
            trend={{ value: 8, isPositive: true }}
          />
        </section>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          {/* Left Column - Chart & Rooms */}
          <div className="xl:col-span-2 space-y-6">
            {/* Usage Chart */}
            <UsageChart />

            {/* Rooms Section */}
            <section>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-lg font-semibold text-foreground">Room Status</h2>
                  <p className="text-sm text-muted-foreground">
                    {filteredRooms.length} rooms • {filteredRooms.filter(r => r.status === 'active').length} active
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant={viewMode === 'grid' ? 'default' : 'ghost'}
                    size="icon"
                    onClick={() => setViewMode('grid')}
                    className="h-9 w-9"
                  >
                    <LayoutGrid className="h-4 w-4" />
                  </Button>
                  <Button
                    variant={viewMode === 'list' ? 'default' : 'ghost'}
                    size="icon"
                    onClick={() => setViewMode('list')}
                    className="h-9 w-9"
                  >
                    <List className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              <BuildingFilter 
                selected={selectedBuilding} 
                onSelect={setSelectedBuilding} 
              />

              <div className={cn(
                'mt-4',
                viewMode === 'grid' 
                  ? 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4'
                  : 'space-y-3'
              )}>
                {filteredRooms.map((room, index) => (
                  <RoomCard 
                    key={room.id} 
                    room={room}
                    className={viewMode === 'list' ? 'w-full' : ''}
                    style={{ animationDelay: `${index * 50}ms` }}
                  />
                ))}
              </div>
            </section>
          </div>

          {/* Right Column - Suggestions & Predictions */}
          <div className="space-y-6">
            {/* AI Suggestions */}
            <section>
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 rounded-xl bg-primary/10">
                  <Sparkles className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-foreground">AI Suggestions</h2>
                  <p className="text-sm text-muted-foreground">{suggestions.length} optimization opportunities</p>
                </div>
              </div>

              <div className="space-y-4">
                {suggestions.map((suggestion, index) => (
                  <SuggestionCard 
                    key={suggestion.id} 
                    suggestion={suggestion}
                    style={{ animationDelay: `${index * 100}ms` }}
                  />
                ))}
              </div>
            </section>

            {/* Predictions Panel */}
            <PredictionPanel />
          </div>
        </div>
      </main>
    </div>
  </>);
}
