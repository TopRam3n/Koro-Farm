import { useState, useEffect } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { useToast } from '@/hooks/use-toast';

export interface RoomWithSensor {
  id: string;
  room_code: string;
  name: string;
  building: string;
  floor: number;
  type: 'classroom' | 'lab' | 'lecture-hall' | 'office';
  capacity: number;
  status: 'active' | 'idle' | 'offline';
  currentOccupancy: number;
  energyUsage: number;
  temperature: number;
  lastActivity: string;
  scheduledUntil?: string;
}

export function useRooms() {
  const [rooms, setRooms] = useState<RoomWithSensor[]>([]);
  const [buildings, setBuildings] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const { toast } = useToast();

  const fetchRooms = async () => {
    try {
      // Fetch rooms with their latest sensor reading
      const { data: roomsData, error: roomsError } = await supabase
        .from('rooms')
        .select(`
          *,
          buildings:building_id (name)
        `);

      if (roomsError) throw roomsError;

      // Fetch latest sensor readings for each room
      const roomIds = roomsData?.map(r => r.id) || [];
      const { data: sensorsData, error: sensorsError } = await supabase
        .from('sensor_readings')
        .select('*')
        .in('room_id', roomIds)
        .order('recorded_at', { ascending: false });

      if (sensorsError) throw sensorsError;

      // Group sensor readings by room_id and get latest
      const latestSensors = new Map();
      sensorsData?.forEach(sensor => {
        if (!latestSensors.has(sensor.room_id)) {
          latestSensors.set(sensor.room_id, sensor);
        }
      });

      // Combine room and sensor data
      const combinedRooms: RoomWithSensor[] = roomsData?.map(room => {
        const sensor = latestSensors.get(room.id);
        const recordedAt = sensor?.recorded_at ? new Date(sensor.recorded_at) : null;
        const now = new Date();
        const diffMinutes = recordedAt ? Math.floor((now.getTime() - recordedAt.getTime()) / 60000) : null;

        let lastActivity = 'unknown';
        if (diffMinutes !== null) {
          if (diffMinutes < 1) lastActivity = 'now';
          else if (diffMinutes < 60) lastActivity = `${diffMinutes} min ago`;
          else lastActivity = `${Math.floor(diffMinutes / 60)} hours ago`;
        }

        return {
          id: room.id,
          room_code: room.room_code,
          name: room.name,
          building: room.buildings?.name || 'Unknown',
          floor: room.floor,
          type: room.type as RoomWithSensor['type'],
          capacity: room.capacity,
          status: (sensor?.status || 'offline') as RoomWithSensor['status'],
          currentOccupancy: sensor?.current_occupancy || 0,
          energyUsage: Number(sensor?.energy_usage) || 0,
          temperature: Number(sensor?.temperature) || 22,
          lastActivity,
        };
      }) || [];

      setRooms(combinedRooms);

      // Extract unique buildings
      const uniqueBuildings = [...new Set(combinedRooms.map(r => r.building))];
      setBuildings(uniqueBuildings);
    } catch (error: any) {
      toast({
        title: "Error loading rooms",
        description: error.message,
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchRooms();

    // Subscribe to real-time sensor updates
    const channel = supabase
      .channel('sensor-updates')
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'sensor_readings',
        },
        () => {
          fetchRooms(); // Refetch when sensors update
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  const getMetrics = () => {
    const activeRooms = rooms.filter(r => r.status === 'active').length;
    const idleRooms = rooms.filter(r => r.status === 'idle').length;
    const totalEnergy = rooms.reduce((sum, r) => sum + r.energyUsage, 0);
    const totalOccupancy = rooms.reduce((sum, r) => sum + r.currentOccupancy, 0);
    const totalCapacity = rooms.reduce((sum, r) => sum + r.capacity, 0);

    return {
      activeRooms,
      idleRooms,
      offlineRooms: rooms.filter(r => r.status === 'offline').length,
      totalRooms: rooms.length,
      totalEnergy: totalEnergy.toFixed(1),
      avgOccupancy: totalCapacity > 0 ? Math.round((totalOccupancy / totalCapacity) * 100) : 0,
      potentialSavings: (idleRooms * 1.5).toFixed(1), // Estimate based on idle rooms
    };
  };

  return { rooms, buildings, isLoading, getMetrics, refetch: fetchRooms };
}
