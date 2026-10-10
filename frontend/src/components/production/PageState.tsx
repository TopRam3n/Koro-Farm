import { AlertTriangle, Inbox, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
    return <div className="flex min-h-40 items-center justify-center gap-2 text-sm text-muted-foreground" role="status" aria-live="polite"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />{label}</div>;
}

export function EmptyState({ title = 'Nothing here yet', description }: { title?: string; description?: string }) {
    return <div className="rounded-xl border border-dashed p-8 text-center"><Inbox className="mx-auto h-7 w-7 text-muted-foreground" aria-hidden="true" /><p className="mt-3 font-medium">{title}</p>{description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}</div>;
}

export function ErrorState({ message = 'This data could not be loaded.', onRetry }: { message?: string; onRetry?: () => void }) {
    return <div className="rounded-xl border border-destructive/30 p-8 text-center" role="alert"><AlertTriangle className="mx-auto h-7 w-7 text-destructive" aria-hidden="true" /><p className="mt-3 font-medium">Something went wrong</p><p className="mt-1 text-sm text-muted-foreground">{message}</p>{onRetry && <Button className="mt-4" variant="outline" onClick={onRetry}>Try again</Button>}</div>;
}
