
import { redirect } from 'next/navigation';

export default async function FarmerHistoryPage({
    params,
}: {
    params: Promise<{ id: string }>;
}) {
    const { id } = await params;

    redirect(`/farmers/${id}`);
}
