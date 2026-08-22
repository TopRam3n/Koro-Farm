export type RoomStatus = 'active' | 'idle' | 'offline';
export type RoomType = 'classroom' | 'lab' | 'lecture-hall' | 'office';

export interface Room {
  id: string;
  name: string;
  building: string;
  floor: number;
  type: RoomType;
  capacity: number;
  currentOccupancy: number;
  status: RoomStatus;
  energyUsage: number; // kWh
  temperature: number;
  lastActivity: string;
  scheduledUntil?: string;
}

export interface Suggestion {
  id: string;
  type: 'optimization' | 'warning' | 'insight';
  priority: 'high' | 'medium' | 'low';
  title: string;
  description: string;
  potentialSavings?: string;
  affectedRooms: string[];
}

export interface UsageDataPoint {
  time: string;
  classrooms: number;
  labs: number;
  energy: number;
}

export const buildings = [
  'Science Building',
  'Arts Building', 
  'Engineering Block',
  'Library',
  'Student Center',
];

export const rooms: Room[] = [
  {
    id: 'SCI-101',
    name: 'Chemistry Lab A',
    building: 'Science Building',
    floor: 1,
    type: 'lab',
    capacity: 30,
    currentOccupancy: 24,
    status: 'active',
    energyUsage: 4.2,
    temperature: 22,
    lastActivity: '2 min ago',
    scheduledUntil: '2:00 PM',
  },
  {
    id: 'SCI-102',
    name: 'Chemistry Lab B',
    building: 'Science Building',
    floor: 1,
    type: 'lab',
    capacity: 30,
    currentOccupancy: 0,
    status: 'idle',
    energyUsage: 1.8,
    temperature: 24,
    lastActivity: '45 min ago',
  },
  {
    id: 'SCI-201',
    name: 'Physics Lecture Hall',
    building: 'Science Building',
    floor: 2,
    type: 'lecture-hall',
    capacity: 120,
    currentOccupancy: 87,
    status: 'active',
    energyUsage: 6.5,
    temperature: 21,
    lastActivity: 'now',
    scheduledUntil: '3:30 PM',
  },
  {
    id: 'SCI-203',
    name: 'Biology Lab',
    building: 'Science Building',
    floor: 2,
    type: 'lab',
    capacity: 25,
    currentOccupancy: 0,
    status: 'offline',
    energyUsage: 0,
    temperature: 25,
    lastActivity: '3 hours ago',
  },
  {
    id: 'ENG-101',
    name: 'Computer Lab 1',
    building: 'Engineering Block',
    floor: 1,
    type: 'lab',
    capacity: 40,
    currentOccupancy: 38,
    status: 'active',
    energyUsage: 8.2,
    temperature: 20,
    lastActivity: 'now',
    scheduledUntil: '4:00 PM',
  },
  {
    id: 'ENG-102',
    name: 'Computer Lab 2',
    building: 'Engineering Block',
    floor: 1,
    type: 'lab',
    capacity: 40,
    currentOccupancy: 12,
    status: 'active',
    energyUsage: 5.1,
    temperature: 21,
    lastActivity: '5 min ago',
    scheduledUntil: '1:30 PM',
  },
  {
    id: 'ENG-201',
    name: 'Design Studio',
    building: 'Engineering Block',
    floor: 2,
    type: 'lab',
    capacity: 20,
    currentOccupancy: 0,
    status: 'idle',
    energyUsage: 2.3,
    temperature: 23,
    lastActivity: '1 hour ago',
  },
  {
    id: 'ART-101',
    name: 'Lecture Room A',
    building: 'Arts Building',
    floor: 1,
    type: 'classroom',
    capacity: 50,
    currentOccupancy: 45,
    status: 'active',
    energyUsage: 2.1,
    temperature: 22,
    lastActivity: 'now',
    scheduledUntil: '2:30 PM',
  },
  {
    id: 'ART-102',
    name: 'Lecture Room B',
    building: 'Arts Building',
    floor: 1,
    type: 'classroom',
    capacity: 50,
    currentOccupancy: 0,
    status: 'idle',
    energyUsage: 0.8,
    temperature: 24,
    lastActivity: '2 hours ago',
  },
  {
    id: 'ART-201',
    name: 'Seminar Room 1',
    building: 'Arts Building',
    floor: 2,
    type: 'classroom',
    capacity: 25,
    currentOccupancy: 18,
    status: 'active',
    energyUsage: 1.5,
    temperature: 22,
    lastActivity: '1 min ago',
    scheduledUntil: '1:00 PM',
  },
  {
    id: 'LIB-101',
    name: 'Study Hall A',
    building: 'Library',
    floor: 1,
    type: 'classroom',
    capacity: 80,
    currentOccupancy: 52,
    status: 'active',
    energyUsage: 3.2,
    temperature: 21,
    lastActivity: 'now',
  },
  {
    id: 'LIB-201',
    name: 'Computer Commons',
    building: 'Library',
    floor: 2,
    type: 'lab',
    capacity: 60,
    currentOccupancy: 34,
    status: 'active',
    energyUsage: 7.8,
    temperature: 20,
    lastActivity: 'now',
  },
];

export const suggestions: Suggestion[] = [
  {
    id: '1',
    type: 'optimization',
    priority: 'high',
    title: 'Consolidate Computer Lab Sessions',
    description: 'Computer Lab 2 (ENG-102) has only 30% occupancy. Consider moving the COMP201 class to merge with existing session in Lab 1.',
    potentialSavings: '~5.1 kWh/hour',
    affectedRooms: ['ENG-101', 'ENG-102'],
  },
  {
    id: '2',
    type: 'warning',
    priority: 'high',
    title: 'Chemistry Lab B Running Idle',
    description: 'SCI-102 has been unoccupied for 45 minutes but AC and lights remain on. Recommend automated shutdown.',
    potentialSavings: '~1.8 kWh/hour',
    affectedRooms: ['SCI-102'],
  },
  {
    id: '3',
    type: 'optimization',
    priority: 'medium',
    title: 'Reschedule Design Studio Usage',
    description: 'ENG-201 shows consistent idle periods between 10AM-2PM. Historical data suggests better utilization in evening slots.',
    potentialSavings: '~4.6 kWh/day',
    affectedRooms: ['ENG-201'],
  },
  {
    id: '4',
    type: 'insight',
    priority: 'low',
    title: 'Peak Usage Prediction',
    description: 'ML model predicts 85% campus utilization between 10:00 AM - 12:00 PM tomorrow. Consider pre-cooling high-traffic buildings.',
    affectedRooms: ['SCI-201', 'ENG-101', 'LIB-101'],
  },
  {
    id: '5',
    type: 'optimization',
    priority: 'medium',
    title: 'Arts Building Temperature Optimization',
    description: 'Lecture Room B (ART-102) maintaining 24°C while idle. Raising setpoint to 26°C during vacant periods saves energy.',
    potentialSavings: '~0.5 kWh/hour',
    affectedRooms: ['ART-102'],
  },
];

export const usageData: UsageDataPoint[] = [
  { time: '8AM', classrooms: 45, labs: 30, energy: 42 },
  { time: '9AM', classrooms: 72, labs: 55, energy: 68 },
  { time: '10AM', classrooms: 88, labs: 78, energy: 85 },
  { time: '11AM', classrooms: 92, labs: 85, energy: 91 },
  { time: '12PM', classrooms: 65, labs: 60, energy: 72 },
  { time: '1PM', classrooms: 78, labs: 70, energy: 80 },
  { time: '2PM', classrooms: 85, labs: 82, energy: 88 },
  { time: '3PM', classrooms: 70, labs: 68, energy: 75 },
  { time: '4PM', classrooms: 55, labs: 52, energy: 60 },
  { time: '5PM', classrooms: 35, labs: 40, energy: 45 },
  { time: '6PM', classrooms: 20, labs: 25, energy: 30 },
];

export const getMetrics = () => {
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
    avgOccupancy: Math.round((totalOccupancy / totalCapacity) * 100),
    potentialSavings: '12.4',
  };
};