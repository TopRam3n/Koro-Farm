import { usageData } from '@/lib/mockdata';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

export function UsageChart() {
  return (
    <div className="glass-card rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="font-semibold text-foreground">Usage Trends</h3>
          <p className="text-sm text-muted-foreground">Real-time campus utilization</p>
        </div>
        <div className="flex gap-4 text-sm">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-primary" />
            <span className="text-muted-foreground">Classrooms</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-success" />
            <span className="text-muted-foreground">Labs</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-energy" />
            <span className="text-muted-foreground">Energy</span>
          </div>
        </div>
      </div>
      
      <div className="h-[280px] -mx-2">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={usageData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id="colorClassrooms" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(173, 80%, 40%)" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="hsl(173, 80%, 40%)" stopOpacity={0}/>
              </linearGradient>
              <linearGradient id="colorLabs" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(142, 76%, 36%)" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="hsl(142, 76%, 36%)" stopOpacity={0}/>
              </linearGradient>
              <linearGradient id="colorEnergy" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(262, 83%, 58%)" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="hsl(262, 83%, 58%)" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
            <XAxis 
              dataKey="time" 
              tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis 
              tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => `${value}%`}
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                borderRadius: '8px',
                boxShadow: '0 4px 6px -1px hsl(222 47% 11% / 0.1)',
              }}
              labelStyle={{ color: 'hsl(var(--foreground))', fontWeight: 600 }}
            />
            <Area 
              type="monotone" 
              dataKey="classrooms" 
              stroke="hsl(173, 80%, 40%)" 
              strokeWidth={2}
              fillOpacity={1} 
              fill="url(#colorClassrooms)"
              name="Classrooms"
            />
            <Area 
              type="monotone" 
              dataKey="labs" 
              stroke="hsl(142, 76%, 36%)" 
              strokeWidth={2}
              fillOpacity={1} 
              fill="url(#colorLabs)"
              name="Labs"
            />
            <Area 
              type="monotone" 
              dataKey="energy" 
              stroke="hsl(262, 83%, 58%)" 
              strokeWidth={2}
              fillOpacity={1} 
              fill="url(#colorEnergy)"
              name="Energy"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
