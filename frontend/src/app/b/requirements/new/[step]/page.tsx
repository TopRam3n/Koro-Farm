import { notFound } from 'next/navigation';
import { RequirementWizard } from '@/features/requirements/RequirementWizard';
import { requirementSteps, type RequirementStep } from '@/features/requirements/types';

export default async function NewRequirementStep({ params }: { params: Promise<{ step: string }> }) { const { step } = await params; if (!requirementSteps.includes(step as RequirementStep)) notFound(); return <RequirementWizard step={step as RequirementStep} />; }
