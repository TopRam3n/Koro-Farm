/** Decimal-string arithmetic in thousandths, avoiding binary float arithmetic for canonical kg quantities. */
export function decimalToMillis(value: string | number | null | undefined): number {
    if (value === null || value === undefined || value === '') return 0;
    const raw = String(value).trim();
    const match = raw.match(/^(-?)(\d+)(?:\.(\d+))?$/);
    if (!match) throw new Error(`Invalid decimal: ${raw}`);
    const fraction = `${match[3] ?? ''}000`.slice(0, 3);
    const magnitude = Number(match[2]) * 1000 + Number(fraction);
    if (!Number.isSafeInteger(magnitude)) throw new Error(`Decimal exceeds safe quantity range: ${raw}`);
    return match[1] ? -magnitude : magnitude;
}

export function addDecimalKg(values: Array<string | number | null | undefined>): string {
    const sum = values.reduce<number>((total, value) => total + decimalToMillis(value), 0);
    const negative = sum < 0;
    const magnitude = negative ? -sum : sum;
    const whole = Math.floor(magnitude / 1000);
    const fraction = (magnitude % 1000).toString().padStart(3, '0').replace(/0+$/, '');
    return `${negative ? '-' : ''}${whole}${fraction ? `.${fraction}` : ''}`;
}
