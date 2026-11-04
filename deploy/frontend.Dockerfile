# KoroFarm frontend image (Next.js).
# NEXT_PUBLIC_* values are compiled into the browser bundle at build time, so they are build arguments. They are
# public by design (API URL, Supabase URL, Supabase publishable key); never pass a secret here.
# Build from the repository root:
#   docker build -f deploy/frontend.Dockerfile \
#     --build-arg NEXT_PUBLIC_API_URL=https://api.staging.example.org \
#     --build-arg NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co \
#     --build-arg NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_... \
#     -t korofarm-frontend .
FROM node:22-alpine AS build
WORKDIR /app
COPY src/frontend/package.json src/frontend/package-lock.json ./
RUN npm ci
COPY src/frontend/ ./
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
ARG NEXT_PUBLIC_ACCESS_REQUEST_REVIEWER_EMAIL=""
# Staging and production builds are always live: demo replay is disabled and has no place in a deployed build.
ENV NEXT_PUBLIC_APP_MODE=live \
    NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=$NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY \
    NEXT_PUBLIC_ACCESS_REQUEST_REVIEWER_EMAIL=$NEXT_PUBLIC_ACCESS_REQUEST_REVIEWER_EMAIL \
    NEXT_TELEMETRY_DISABLED=1
RUN test -n "$NEXT_PUBLIC_API_URL" && test -n "$NEXT_PUBLIC_SUPABASE_URL" && test -n "$NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY" \
    || (echo "NEXT_PUBLIC_API_URL, NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY are required" && exit 1)
# The build fails if anything from the test-only auth stand-in reached the bundle.
RUN npm run build && npm run check:bundle && npm prune --omit=dev

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build --chown=node:node /app/package.json ./package.json
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/.next ./.next
COPY --from=build --chown=node:node /app/public ./public
COPY --from=build --chown=node:node /app/next.config.mjs ./next.config.mjs
USER node
EXPOSE 3000
CMD ["npx", "next", "start", "-H", "0.0.0.0", "-p", "3000"]
