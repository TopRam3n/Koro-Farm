export type SupplyHealth = 'COVERED' | 'AT_RISK' | 'RECOVERED' | 'ESCALATION_REQUIRED';
export type AllocationRole = 'COMMITTED' | 'STANDBY';
export type AllocationStatus = 'COMMITTED' | 'STANDBY' | 'ACTIVATED' | 'LOST';

export interface Allocation {
  id: string;
  farmer: string;
  farmerId: string;
  parish: string;
  lotId: string;
  quantityKg: number;
  role: AllocationRole;
  status: AllocationStatus;
}

export interface SupplyMetrics {
  requiredKg: number;
  committedKg: number;
  standbyKg: number;
  shortfallKg: number;
  committedFarmerCount: number;
  standbyFarmerCount: number;
  health: SupplyHealth;
}

export interface RecoveryStep {
  label: string;
  detail: string;
  state: 'complete' | 'active' | 'pending';
}

export const requirement = {
  id: 'REQ-HOTEL-001',
  buyer: 'Blue Mountain Lodge',
  buyerType: 'Institutional hotel',
  destination: 'Montego Bay, Jamaica',
  crop: 'Fresh ginger',
  grade: 'Grade A',
  deliveryWindow: '01-02 Sep 2026',
};

export const supplyMetrics: SupplyMetrics = {
  requiredKg: 500,
  committedKg: 500,
  standbyKg: 120,
  shortfallKg: 0,
  committedFarmerCount: 8,
  standbyFarmerCount: 3,
  health: 'RECOVERED',
};

export const allocations: Allocation[] = [
  { id: 'A-001', farmer: 'Mavis Thompson', farmerId: 'F-001', parish: 'Manchester', lotId: 'LOT-MAN-01', quantityKg: 50, role: 'COMMITTED', status: 'COMMITTED' },
  { id: 'A-002', farmer: 'Leon Reid', farmerId: 'F-002', parish: 'St. Elizabeth', lotId: 'LOT-STE-04', quantityKg: 72, role: 'COMMITTED', status: 'COMMITTED' },
  { id: 'A-003', farmer: 'Owen Campbell', farmerId: 'F-003', parish: 'Clarendon', lotId: 'LOT-CLA-02', quantityKg: 64, role: 'COMMITTED', status: 'COMMITTED' },
  { id: 'A-004', farmer: 'Renee Brown', farmerId: 'F-004', parish: 'St. Ann', lotId: 'LOT-STA-08', quantityKg: 58, role: 'COMMITTED', status: 'COMMITTED' },
  { id: 'A-005', farmer: 'Damian Grant', farmerId: 'F-005', parish: 'St. Mary', lotId: 'LOT-STM-03', quantityKg: 55, role: 'COMMITTED', status: 'COMMITTED' },
  { id: 'A-006', farmer: 'Althea Morgan', farmerId: 'F-006', parish: 'Portland', lotId: 'LOT-POR-05', quantityKg: 61, role: 'COMMITTED', status: 'COMMITTED' },
  { id: 'A-007', farmer: 'Curtis Hall', farmerId: 'F-007', parish: 'Westmoreland', lotId: 'LOT-WES-02', quantityKg: 60, role: 'COMMITTED', status: 'COMMITTED' },
  { id: 'A-008', farmer: 'Nadine Ellis', farmerId: 'F-008', parish: 'Hanover', lotId: 'LOT-HAN-01', quantityKg: 80, role: 'COMMITTED', status: 'COMMITTED' },
  { id: 'A-009', farmer: 'Peter Wallace', farmerId: 'F-009', parish: 'St. Catherine', lotId: 'LOT-STC-06', quantityKg: 50, role: 'STANDBY', status: 'STANDBY' },
  { id: 'A-010', farmer: 'Shanice Forbes', farmerId: 'F-010', parish: 'Trelawny', lotId: 'LOT-TRE-02', quantityKg: 40, role: 'STANDBY', status: 'STANDBY' },
  { id: 'A-011', farmer: 'Everton Clarke', farmerId: 'F-011', parish: 'Kingston', lotId: 'LOT-KIN-01', quantityKg: 30, role: 'STANDBY', status: 'STANDBY' },
];

export const recoverySteps: RecoveryStep[] = [
  { label: 'Disruption detected', detail: 'Nadine Ellis dropped 80 kg from committed supply', state: 'complete' },
  { label: 'Requirement marked at risk', detail: '420 kg remained against the 500 kg SLA', state: 'complete' },
  { label: 'Standby capacity activated', detail: '80 kg activated from Peter Wallace reserve lot', state: 'complete' },
  { label: 'Buyer SLA restored', detail: '500 kg committed; no human escalation required', state: 'complete' },
];

export const economics = {
  originalCost: 186800,
  recoveredCost: 191400,
  premium: 4600,
  premiumPercent: 2.46,
};

export const fulfilment = {
  node: 'St. James Collection Hub',
  status: 'Awaiting receipt',
  requiredKg: 500,
  receivedKg: 0,
  acceptedKg: 0,
  rejectedKg: 0,
};

export const formatJmd = (value: number) => `J$${value.toLocaleString('en-JM')}`;
