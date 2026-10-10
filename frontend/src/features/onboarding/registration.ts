export const SIGNUP_PERSONA_KEY = 'korofarm.signup-persona';
export const ONBOARDING_EMAIL_KEY = 'korofarm.onboarding-email';

export function onboardingDestination(persona: 'FARMER' | 'BUYER') {
    return persona === 'FARMER' ? '/onboarding/farmer-contact' : '/onboarding/buyer-organization';
}
