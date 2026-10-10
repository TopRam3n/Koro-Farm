import { describe, expect, it } from 'vitest';
import { addDecimalKg, decimalToMillis } from './decimal';

describe('decimal-safe quantities', () => {
    it('parses canonical decimal quantities without floating point arithmetic', () => expect(decimalToMillis('0.1')).toBe(100));
    it('adds decimal quantities exactly', () => expect(addDecimalKg(['0.1', '0.2', '12.345'])).toBe('12.645'));
    it('preserves signed quantities', () => expect(addDecimalKg(['10.125', '-0.125'])).toBe('10'));
});
