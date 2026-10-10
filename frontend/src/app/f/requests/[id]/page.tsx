import { notFound } from 'next/navigation';
import { farmerRequests } from '@/features/farmerRequests/fixtures';
import { RequestEvaluation } from '@/features/farmerRequests/RequestEvaluation';

export default async function FarmerRequestPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = await params;
    const request = farmerRequests.find(item => item.id === id);
    if (!request) notFound();
    return <RequestEvaluation request={request} />;
}
