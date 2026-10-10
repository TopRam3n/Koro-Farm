# Frontend baseline

Recorded 1 September 2026.

- Framework: Next.js 16.3.2 with App Router.
- React: 18.3.1.
- TypeScript: 5.8.3.
- Unit tests: Vitest 3.2.4; baseline suite passes (1/1).
- Production build: passes after removing the accidental legacy `src/pages` routing surface by moving reusable views to `src/views`.
- Build emits non-blocking workspace-root and Browserslist data-age warnings.

Vitest is configured without a Vite React transform plugin because current tests target TypeScript/domain logic. React component tests can introduce a compatible transform only when required.
