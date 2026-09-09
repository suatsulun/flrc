# flrc-web: both compiled SPAs, the same-origin /api proxy, automatic TLS, and
# the runtime branding overlay, in one Caddy container (ADR-053, ADR-054).
# Build context is the repository root: docker build -f infra/web/Dockerfile .

FROM node:26-bookworm-slim@sha256:367679cf9792759492a486e4aa4b421764d71a9546a6dae8aab81a99eb797b3e AS build
# Node no longer bundles Corepack; install the pinned pnpm explicitly (ADR-026).
RUN npm install --global pnpm@11.25.0
# Non-interactive, no git hooks, and patient with a slow registry mirror.
ENV CI=true LEFTHOOK=0 npm_config_fetch_retries=5 npm_config_fetch_timeout=300000
WORKDIR /repo
# Manifests first so dependency installation is cached across source changes.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
# Every workspace manifest, so the project set pnpm records at install time is
# the same one it sees after the full copy below; a difference would make its
# pre-run check reinstall, which the .npmrc line also forbids.
COPY apps/teacher/package.json apps/teacher/
COPY apps/admin/package.json apps/admin/
COPY apps/backend/package.json apps/backend/
COPY packages/ui/package.json packages/ui/
COPY packages/api-client/package.json packages/api-client/
COPY packages/i18n/package.json packages/i18n/
COPY branding/package.json branding/
# The whole workspace, so pnpm's pre-run dependency check finds nothing missing
# and never re-installs. --ignore-scripts skips the root `prepare` hook (lefthook
# needs a git checkout); dependency build scripts stay governed by allowBuilds.
RUN printf 'verify-deps-before-run=false\n' > .npmrc \
    && pnpm install --frozen-lockfile --ignore-scripts
COPY . .
# Both apps share one origin on the school box, so the cross-links are relative.
ARG VITE_ADMIN_URL=/admin/
ARG VITE_TEACHER_URL=/
ENV VITE_ADMIN_URL=$VITE_ADMIN_URL VITE_TEACHER_URL=$VITE_TEACHER_URL
RUN pnpm brand && pnpm --filter @flrc/teacher build && pnpm --filter @flrc/admin build

FROM caddy:2-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648
COPY infra/web/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /repo/apps/teacher/dist /srv/teacher
COPY --from=build /repo/apps/admin/dist /srv/admin
# Generic identity, served when the mounted overlay lacks a file.
COPY --from=build /repo/apps/teacher/public/branding /srv/branding-default
RUN mkdir -p /srv/branding && caddy validate --config /etc/caddy/Caddyfile
EXPOSE 80 443
