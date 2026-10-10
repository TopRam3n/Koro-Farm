# KoroFarm Frontend Implementation Overview

The KoroFarm frontend is implemented as a Next.js 16 and React 18 application that presents a supply-assurance control room for agricultural procurement in Jamaica. The application focuses on turning multiple smallholder farmer allocations into a traceable institutional supply commitment and visually communicating supply coverage, disruption recovery, fulfilment status, and cost impact. Routing is implemented with the Next.js App Router, while the application UI is split into page-level views and reusable React components. Tailwind CSS utility classes provide the responsive layout and styling, shadcn/Radix-based UI components provide reusable controls such as cards, badges, buttons, inputs, tooltips and toast notifications, and Lucide React supplies the interface icons.

## Application structure and routing

The root Next.js layout defines the KoroFarm supply-assurance metadata and wraps all pages in a shared provider layer. That provider layer installs TanStack Query's query client, next-themes for system-aware light and dark themes, tooltip support, Supabase authentication state, and both toast notification systems. The App Router exposes the dashboard at `/`, authentication at `/login` and `/signup`, and account/activity views at `/profile` and `/notifications`. The dashboard route is additionally wrapped in an authentication gate, which displays a loading indicator while session state is being resolved and redirects unauthenticated users to the login page.

## Authentication and user accounts

User authentication is implemented with Supabase Auth. A React authentication context maintains the current Supabase user, session, and loading state. On application startup it registers an authentication-state listener and separately checks for an existing session, allowing the UI to react to login, logout and restored browser sessions. The login form uses controlled React state for email and password and calls Supabase's password sign-in API. Successful authentication displays a toast and routes the user to the dashboard; failures produce destructive error notifications. Signup is similarly implemented with Supabase Auth and collects a display name, email and password. The display name is stored in Supabase user metadata, the password has client-side minimum-length validation, and an email redirect URL is supplied during account creation.

The profile view consumes the shared authentication context rather than maintaining a second copy of account state. It derives a readable display name from user metadata, falling back to the email username when necessary. It presents the user's email together with demo programme information such as the programme-operator role, Jamaican operating region and active status. Signing out calls the central Supabase sign-out method and returns the browser to the login route.

## Main supply-assurance dashboard

The main dashboard is composed from dedicated React presentation components. Its current procurement scenario is driven by typed mock data representing a 500 kg Grade A fresh ginger requirement for Blue Mountain Lodge in Montego Bay. The data model includes requirement information, supply metrics, individual farmer allocations and production lot identifiers, recovery activity, landed-cost economics, and collection-node fulfilment. This gives the interface deterministic structured state while the backend workflow is being represented as a demo programme.

The supply overview calculates coverage dynamically by dividing committed kilograms by required kilograms and converting the result to a percentage. It renders the result as both text and a visual progress bar and displays required supply, standby reserve, committed and reserve farmer counts, current shortfall, supply-health state, and the number of traceable production lots. Status badges and colour semantics make preserved, recovered and standby states visible without changing the underlying supply data.

Farmer allocation traceability is implemented as a horizontally responsive supply-ledger table. Each allocation has a farmer name and ID, parish, production lot ID, quantity, role and status in the typed data model. The rendered table distinguishes committed and standby allocations with status badges, while retaining the farmer-to-lot relationship needed for traceability. The current scenario consists of eight committed farmers and three standby farmers distributed across Jamaican parishes.

## Disruption recovery and supply assurance

The recovery panel implements an explicit visual audit sequence for a supply disruption. In the demo scenario, an 80 kg loss from Nadine Ellis reduces the committed position from 500 kg to 420 kg, marks the requirement at risk, activates 80 kg of reserve capacity from Peter Wallace, and restores the buyer commitment to 500 kg. These actions are represented as typed recovery steps and rendered as a completed vertical timeline. The interface explicitly states that quantity and cost decisions are deterministic and that physical fulfilment is not claimed until receipt and grading evidence exists. This separation between commitment recovery and verified fulfilment is an important part of the frontend's assurance model.

## Economics and fulfilment

The economics panel communicates the financial consequence of recovery using structured Jamaican-dollar values. It compares the original landed cost of J$186,800 with a recovered cost of J$191,400 and displays the J$4,600, or 2.46%, recovery premium. Currency output is normalized through a formatter using the `en-JM` locale rather than embedding differently formatted currency strings throughout the UI.

Physical fulfilment is represented separately through the St. James Collection Hub panel. It tracks required, received, accepted and rejected quantities and currently marks the consignment as awaiting receipt. This component deliberately shows zero kilograms received, accepted and rejected until evidence is available, and tells the operator that receipt evidence is required before reconciliation. In other words, the frontend distinguishes planned or committed supply from physically verified supply.

## Header, navigation, theme and introductory experience

The global dashboard header contains KoroFarm branding, a demo-programme marker, a live client-side clock and date, notification navigation, a dashboard refresh control, theme switching and profile navigation. The clock is implemented with React state and a one-second interval that is cleaned up when the component unmounts. Theme switching is implemented with `next-themes`; it reads the resolved theme and changes between light and dark modes. Navigation to profile and notifications uses Next.js client navigation through `Link` components.

The dashboard also has an animated introductory overlay implemented with GSAP. On the first dashboard visit in a browser tab, the component uses `sessionStorage` to record that the intro has played. A GSAP timeline reveals the "Guarantee Your Supply" text, performs a slider wipe, moves the intro screen away, and finally disables pointer events on the departed overlays. GSAP context cleanup is used so animation effects are reverted correctly when React unmounts the component. Subsequent visits in the same tab omit the animation.

## Notifications

The notifications page implements a visual activity feed showing important programme events: preservation of the buyer SLA, the recorded 80 kg disruption, and the pending fulfilment checkpoint. It maps a structured local notification array into cards with timestamps, semantic icons and badges. At present this feed is demo/static frontend data rather than a database-backed notification stream.

## Supabase data and real-time capabilities implemented in hooks

Beyond the mock-data dashboard, the codebase contains data hooks for live room/sensor data and AI predictions. The room hook reads rooms and their building relationship from Supabase, reads sensor measurements ordered by recording time, selects the most recent reading for each room, combines those records into a frontend room model, and derives human-readable last-activity values. It can calculate active, idle and offline room counts, energy usage, aggregate occupancy and estimated savings. It also creates a Supabase Postgres Changes subscription on sensor readings and refetches room information whenever sensor data changes.

The prediction hook invokes a Supabase Edge Function named `ml-predictions` with a POST request. Its response model supports occupancy and energy predictions, confidence values, optimization/warning/insight suggestions, and peak alerts. Stored active AI suggestions are also queried from the `ai_suggestions` Supabase table and ordered by creation time. A Supabase real-time subscription refreshes those suggestions whenever their table changes. Error handling includes dedicated toast messages for rate-limit and AI-credit failures; for general prediction failures, the frontend generates time-aware fallback occupancy and energy predictions locally so prediction display data can remain available. These hooks are implemented in the repository but are not currently connected to the supply-assurance dashboard shown on `/`.

## Supabase connectivity

Browser-side Supabase access is implemented through `@supabase/ssr`'s browser client. The URL and publishable key are read from public Next.js environment variables and exposed through a shared Supabase client instance. This client is reused by authentication, room/sensor queries, AI suggestion queries, real-time subscriptions and Edge Function invocation, avoiding independent client setup in each feature.

## Responsive UI and component methodology

The frontend uses component composition rather than building the dashboard as one monolithic page. Supply status, recovery, allocations, economics, fulfilment, header/navigation, authentication and introductory animation each have their own component boundaries. Tailwind responsive breakpoints change dashboard grids and content arrangements for smaller and larger screens, while the allocation table uses horizontal overflow to remain usable on narrow devices. UI primitives are sourced from the project's reusable component library, and semantic theme tokens such as primary, success, warning, destructive, background and muted colours are used throughout instead of hard-coded component-specific colours.

Overall, the implemented frontend combines a working Next.js user interface, Supabase authentication, route protection, account handling, theming, notifications, animation, a traceable supply-allocation dashboard, disruption recovery visualization, economics and fulfilment state. The dashboard's agricultural scenario is currently backed mainly by typed mock data, while live Supabase-backed room/sensor and AI-prediction infrastructure exists as reusable hooks but is not wired into that dashboard. This distinction is important: the supply workflow UI is implemented and demonstrable, authentication is genuinely Supabase-backed, and the repository contains live data integration capabilities, but the displayed supply requirement, farmer ledger, recovery sequence, economics, fulfilment figures and notification events are currently demo data rather than records fetched from a production supply backend.
