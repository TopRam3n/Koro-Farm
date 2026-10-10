import { notFound } from 'next/navigation';
import { SignupAccount } from '@/features/onboarding/SignupAccount';

export default async function PersonaSignup({ params }: { params: Promise<{ persona: string }> }) {
    const { persona } = await params;
    if (persona !== 'farmer' && persona !== 'buyer') notFound();
    return <SignupAccount persona={persona === 'farmer' ? 'FARMER' : 'BUYER'} />;
}
