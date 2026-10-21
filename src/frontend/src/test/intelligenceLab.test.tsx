import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import artifact from '../../public/agriculture/intelligence.json';
import { IntelligenceContent } from '@/components/IntelligenceLab';
import { AgriculturalIntelligence } from '@/lib/agriculturalIntelligence';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AreaChart: () => <div />, LineChart: () => <div />, Area: () => null, Line: () => null,
  CartesianGrid: () => null, XAxis: () => null, YAxis: () => null, Tooltip: () => null,
}));

describe('official agricultural intelligence', () => {
  it('distinguishes observed records, retrospective forecasts and disputed cells', () => {
    render(<IntelligenceContent data={artifact as AgriculturalIntelligence} />);
    expect(screen.getByText('2026 Q1: 4,069 tonnes')).toBeInTheDocument();
    expect(screen.getByText('Experimental forecast — not a verified shortage prediction')).toBeInTheDocument();
    expect(screen.getByText('39 / 40 production records')).toBeInTheDocument();
    expect(screen.getByText('Quarantined: 2016 Q3 production')).toBeInTheDocument();
    expect(screen.getByText('Unavailable')).toBeInTheDocument();
    expect(screen.getByText(/not a current-quarter forecast/)).toBeInTheDocument();
    expect(screen.getByText(/not an untouched independent holdout/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name:/^Lettuce and chicory$/ })).toBeInTheDocument();
    expect(screen.getByText(/not mapped to Ministry iceberg lettuce/)).toBeInTheDocument();
    expect(screen.getByText(/1,496 annual production and harvested-area observations/)).toBeInTheDocument();
  });
  it('shows unavailable forecast rather than rendering missing estimates as zero', () => {
    const data = structuredClone(artifact) as AgriculturalIntelligence;
    data.experiment.forecast.status = 'unavailable';
    data.experiment.forecast.value_tonnes = null;
    data.experiment.forecast.unavailable_reason = 'Insufficient validated historical data';
    render(<IntelligenceContent data={data} />);
    expect(screen.getByText('Forecast unavailable — insufficient validated historical data')).toBeInTheDocument();
    expect(screen.queryByText('2026 Q1: 0 tonnes')).not.toBeInTheDocument();
  });
  it('renders an unavailable state for syntactically valid incomplete artifacts', () => {
    render(<IntelligenceContent data={{ schema_version: 1, series: [] } as unknown as AgriculturalIntelligence} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Agricultural intelligence unavailable');
  });
  it('rejects omitted calendar quarters instead of shifting seasonal history', () => {
    const data = structuredClone(artifact) as AgriculturalIntelligence;
    data.series.splice(2, 1);
    render(<IntelligenceContent data={data} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Agricultural intelligence unavailable');
  });
  it('renders empty history with no invented cutoff or forecast value', () => {
    const data = structuredClone(artifact) as AgriculturalIntelligence;
    data.series = [];
    data.experiment.forecast.status = 'unavailable';
    data.experiment.forecast.value_tonnes = null;
    data.experiment.forecast.period = null;
    data.experiment.forecast.data_cutoff = null;
    data.experiment.forecast.unavailable_reason = 'No historical observations';
    render(<IntelligenceContent data={data} />);
    expect(screen.getByText('Forecast unavailable — insufficient validated historical data')).toBeInTheDocument();
    expect(screen.queryByText('2026 Q1: 0 tonnes')).not.toBeInTheDocument();
  });
});
