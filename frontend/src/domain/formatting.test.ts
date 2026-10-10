import { describe, expect, it } from 'vitest';
import { formatJmd, formatKg } from './types';

describe('production formatters', () => {
    it('formats JMD consistently', () => expect(formatJmd('1234.50')).toMatch(/\$1,234\.5/));
    it('formats decimal quantities for display', () => expect(formatKg('1234.56')).toBe('1,234.6 kg'));
    it('uses an em dash for unavailable quantities', () => expect(formatKg(null)).toBe('—'));
});
