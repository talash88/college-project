# Step 17: multi-stage production image for the Next.js frontend.
#
# Build from the repository root:
#   docker build -f frontend/Dockerfile \
#     --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 \
#     -t campusxolve-frontend:prod .
#
# NEXT_PUBLIC_* values are inlined at build time by Next.js, so the build arg
# must match the URL browsers will use to reach the backend.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000

FROM node:20-alpine AS deps
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
COPY --from=deps /app/node_modules ./node_modules
COPY frontend/ ./
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
# Next.js `output: 'standalone'` emits a self-contained server; copy it plus
# the static assets and public dir. Source and dev cache stay in prior stages.
COPY --from=builder --chown=appuser:appgroup /app/.next/standalone ./
COPY --from=builder --chown=appuser:appgroup /app/.next/static ./.next/static
USER appuser
EXPOSE 3000
ENV PORT=3000
CMD ["node", "server.js"]
