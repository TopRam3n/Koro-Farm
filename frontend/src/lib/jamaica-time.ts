const JAMAICA_TIME_ZONE = 'America/Jamaica';

export function formatJamaicaDateTime(value: string | number | Date, options: Intl.DateTimeFormatOptions = {}) {
    return new Intl.DateTimeFormat('en-JM', {
        timeZone: JAMAICA_TIME_ZONE,
        dateStyle: 'medium',
        timeStyle: 'short',
        ...options,
    }).format(new Date(value));
}

export { JAMAICA_TIME_ZONE };
