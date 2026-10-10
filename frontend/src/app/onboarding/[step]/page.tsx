import { notFound } from 'next/navigation'; import { OnboardingStep } from '@/features/onboarding/OnboardingStep'; import { isOnboardingStep } from '@/features/onboarding/steps';
export default async function Page({ params }: { params: Promise<{ step: string }> }) { const { step } = await params; if (!isOnboardingStep(step)) notFound(); return <OnboardingStep step={step} /> }
