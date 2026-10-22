
'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AuthGate } from '@/components/AuthGate';
import { apiFetch } from '@/lib/api';

type CurrentUser = {
    active_farmer_id: string | null;
};

function MyFarmerHistory() {
    const router = useRouter();
    const [error, setError] = useState('');

    useEffect(() => {
        let cancelled = false;

        async function load() {
            try {
                const user = await apiFetch<CurrentUser>('/me');

                if (cancelled) return;

                if (!user.active_farmer_id) {
                    setError('No farmer profile is linked to your account.');
                    return;
                }

                router.replace(`/farmers/${user.active_farmer_id}/`);
            } catch (err) {
                if (!cancelled) {
                    setError(
                        err instanceof Error
                            ? err.message
                            : 'Unable to load your farmer history.'
                    );
                }
            }
        }

        void load();

        return () => {
            cancelled = true;
        };
    }, [router]);

    return (
        <main className="mx-auto max-w-5xl p-8">
            {error ? (
                <p role="alert" className="text-red-600">{error}</p>
            ) : (
                <p>Opening your production history...</p>
            )}
        </main>
    );
}

export default function Page() {
    return (
        <AuthGate>
            <MyFarmerHistory />
        </AuthGate>
    );
}
