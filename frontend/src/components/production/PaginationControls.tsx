import { Button } from '@/components/ui/button';

export function PaginationControls({ offset, limit, total, onChange }: { offset: number; limit: number; total: number; onChange: (offset: number) => void }) {
    if (total <= limit) return null;
    const start = total ? offset + 1 : 0;
    const end = Math.min(offset + limit, total);
    return <nav className="mt-5 flex flex-wrap items-center justify-between gap-3" aria-label="Results pagination"><p className="text-sm text-muted-foreground">Showing {start}–{end} of {total}</p><div className="flex gap-2"><Button variant="outline" disabled={offset <= 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</Button><Button variant="outline" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next</Button></div></nav>;
}
