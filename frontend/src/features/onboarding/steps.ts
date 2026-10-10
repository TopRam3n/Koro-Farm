export const onboardingSteps = ['farmer-contact', 'farmer-parish', 'farmer-capability', 'buyer-organization', 'buyer-needs'] as const;

export type OnboardingStepId = (typeof onboardingSteps)[number];

export function isOnboardingStep(value: string): value is OnboardingStepId {
    return (onboardingSteps as readonly string[]).includes(value);
}
