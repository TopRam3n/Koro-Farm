import { notFound } from 'next/navigation';
import { CommitmentDetail } from '@/features/commitments/CommitmentDetail';
import { farmerCommitments } from '@/features/commitments/fixtures';

export default async function CommitmentPage({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; const commitment = farmerCommitments.find(item => item.id === id); if (!commitment) notFound(); return <CommitmentDetail commitment={commitment} />; }
