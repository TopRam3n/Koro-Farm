# KoroFarm routing convention

KoroFarm uses the Next.js App Router. Route files live under `src/app`; reusable page views and feature UI must not live under `src/pages`, because Next.js also interprets that directory as the legacy Pages Router.

## Route ownership

- Public routes: `/`, `/login`, `/login/verify`, `/signup`, `/signup/farmer`, `/signup/buyer`, `/onboarding/:step`, `/r/:token`, `/methodology`, and legal pages.
- Buyer routes use the `/b` namespace.
- Farmer routes use the `/f` namespace.
- Operations routes use the `/ops` namespace.
- Demo/developer tooling uses `/dev/demo` and must be build/environment gated.

Route files should be thin composition boundaries. Shared product UI belongs in `src/features`, reusable page-level views may live in `src/views`, shared persona shells belong in `src/layouts`, and canonical business state belongs in `src/domain`.

## Access rules

Protected persona routes require authentication and authorization. Authentication alone does not grant a persona. Authorization must ultimately come from protected application data/backend policy, not user-editable profile metadata. Unauthenticated protected access redirects to `/login`; multi-persona users may explicitly switch contexts.

The signed-response route `/r/:token` is public only in the routing sense: tokens must be expiring, signed, and narrowly scoped to the encoded action. Demo controls must never be exposed by production builds.
