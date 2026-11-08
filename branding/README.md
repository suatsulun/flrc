# Branding source files

This folder supplies the generic public application identity. Read this when editing these files; the complete source-generation, runtime-overlay and private report contract is in [Branding and private report assets](../docs/operations/branding.md).

| File                  | Role                                                                  |
| --------------------- | --------------------------------------------------------------------- |
| `brand.json`          | Required `name` and six-digit hex `accentColor`; optional `shortName` |
| `logo.svg`            | Required generic logo                                                 |
| `favicon.svg`         | Optional browser icon; falls back to the logo                         |
| `src/index.ts`        | Shared application exports and runtime identity overrides             |
| `generated/brand.css` | Generated colour token input; do not hand-edit                        |

From the application root, regenerate after changing generic source assets:

```bash
pnpm brand
```

`pnpm brand:check` detects drift; `pnpm brand:test` covers the generator. Generated frontend/report files must stay synchronized with this folder.

Keep this checkout generic: **never commit real institution names, domains, personnel, logos or signatures**. Schools use a private deployment runtime overlay, not edits to these public defaults. Private report templates/principal assets require a separate public-only web mount; teacher signatures live in the database. Follow the [canonical branding guide](../docs/operations/branding.md) for formats, mounts, reloads and verification.
