import { AuthGate } from '@/components/AuthGate';
import { FarmerHistoryProfile } from '@/components/FarmerHistoryProfile';

export default async function Page({
    params,
}: {
    params: Promise<{ id: string }>;
}) {
    const { id } = await params;

    return (
        <AuthGate>
            <FarmerHistoryProfile farmerId={id} />
        </AuthGate>
    );
}