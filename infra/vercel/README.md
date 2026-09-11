# Public demo web project

One Vercel project serves the whole demo web tier (ADR-064): the teacher build at `/`, the admin
build at `/admin/`, and a rewrite of `/api/*` to the Render API. This is the same path layout the
school image serves with Caddy, so the routing rules of ADR-022 exist in one configuration per
profile.

`@flrc/demo-web` is a workspace package that depends on both apps. Turborepo therefore builds
`@flrc/teacher` and `@flrc/admin` first, and this package's `build` runs `assemble.mjs`, which
copies both outputs into `dist/` and refuses a bundle that still links to a Vite development port.
The `js` CI job builds this package, so the assembled layout is verified on every pull request.

## Vercel project settings

| Setting                              | Value                                                |
| ------------------------------------ | ---------------------------------------------------- |
| Git repository                       | `suatsulun/flrc`, production branch `main`           |
| Root Directory                       | `infra/vercel`                                       |
| Include files outside Root Directory | enabled (the build needs the whole workspace)        |
| Framework Preset                     | Other                                                |
| Install, Build, Output Directory     | taken from `vercel.json` (leave the overrides empty) |
| Environment variables                | none required                                        |
| Domain                               | `flrc.suatsulun.com` attached to this project only   |

Production builds link the panels to `/admin/` and `/` by default. `VITE_ADMIN_URL` (a full URL or
path to the admin panel) and `VITE_TEACHER_URL` (the teacher origin without a trailing slash) exist
only for layouts that serve the panels from different origins, such as the two-port CI preview; do
not set them here.

## Local check

```bash
pnpm turbo run build --filter=@flrc/demo-web
ls infra/vercel/dist/index.html infra/vercel/dist/admin/index.html
```

## After a deploy

```bash
curl -sI https://flrc.suatsulun.com/admin/ | grep -iE '^(HTTP|location)'   # 308 to /admin
curl -sI https://flrc.suatsulun.com/admin | grep -i '^HTTP'                  # 200
curl -sI https://flrc.suatsulun.com/api/healthz | grep -i '^HTTP'            # 204
```
