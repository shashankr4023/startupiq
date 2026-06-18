# Multi-stage build for the Next.js frontend.
#   Stage 1 (builder): install deps + run `next build`.
#   Stage 2 (runner):  copy only the standalone output -> a small final image.

# ---- Stage 1: build ----
FROM node:20-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_* vars are baked into the browser bundle AT BUILD TIME, so they
# must be present now (passed as build args from docker-compose.yml). The
# Supabase anon key is public by design; the API base points at the nginx origin.
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

RUN npm run build

# ---- Stage 2: runtime ----
FROM node:20-alpine AS runner
WORKDIR /app
# HOSTNAME=0.0.0.0 makes the standalone server bind to all interfaces so nginx
# (a different container) can reach it - the default 'localhost' would not be.
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000

# The standalone output contains a minimal server + only the traced deps.
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
