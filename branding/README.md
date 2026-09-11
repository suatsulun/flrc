# Branding

**This folder is the only place you change to put a school's identity on the product.**

Two required files, an optional favicon, and one command:

| Change this   | To set                                                               |
| ------------- | -------------------------------------------------------------------- |
| `logo.svg`    | The logo on every screen, the sign-in page, and every report card    |
| `brand.json`  | The school's name, short name, and accent colour                     |
| `favicon.svg` | The browser tab icon (optional; `logo.svg` is used if you delete it) |

Then run:

```bash
pnpm brand
```

That is the whole rebrand. `pnpm dev` and `pnpm build` run it for you, so in normal
work you never have to remember it.

---

## brand.json

```json
{
  "name": "Deutsche Schule Istanbul",
  "shortName": "DS Istanbul",
  "accentColor": "#1c62b6"
}
```

| Field         | Required | Used for                                                           |
| ------------- | -------- | ------------------------------------------------------------------ |
| `name`        | yes      | Report-card masthead. Use the full, formal name.                   |
| `shortName`   | no       | Top bar and browser tab, where space is tight. Defaults to `name`. |
| `accentColor` | yes      | The school's colour, as 6-digit hex. Drives the whole palette.     |

### What `accentColor` actually does

The product takes the **hue** of your colour and keeps its own carefully chosen
lightness and saturation. So `#1c62b6` and `#4d8ae0` produce the same palette:
both are the same blue hue.

This is deliberate. If the palette used your exact colour, a school with a pale
yellow or a very dark navy would end up with buttons whose label text is
unreadable. Taking only the hue means any school colour produces a palette that
still clears the 4.5:1 contrast minimum for text.

`pnpm brand` prints what it derived, so you can see the result before looking at
the app:

```
Deutsche Schule Istanbul  (DS Istanbul)
accent #1c62b6 → hue 255.8° → primary #1b62b6 (6.05:1 on white)
```

If you need the exact corporate colour reproduced pixel-for-pixel rather than
matched by hue, that is a design-token change in
`packages/ui/src/styles/theme.css`, not a branding change.

---

## What `pnpm brand` writes

Most of the product reads this folder directly: the web apps import
`@flrc/branding`. Three kinds of consumer cannot, so the tool feeds them:

| Written file                                           | Why it cannot read this folder directly      |
| ------------------------------------------------------ | -------------------------------------------- |
| `branding/generated/brand.css`                         | CSS needs the accent hue as a literal number |
| `apps/{teacher,admin}/public/favicon.svg`              | `index.html` cannot import a JS module       |
| `apps/{teacher,admin}/index.html` title + theme-colour | same                                         |
| `apps/backend/src/flrc/modules/reports/assets/`        | The Docker image only copies `src/`          |
| `apps/{teacher,admin}/public/branding/`                | The runtime overlay described below          |

These are committed, so a fresh clone works without running the tool. CI runs
`pnpm brand:check`, which fails if any of them has drifted from this folder, so a
half-applied rebrand cannot reach `main`.

---

## Rebranding a deployment without a rebuild

A school deployment does not check out this repository; it runs the published
images (ADR-053). Its identity therefore lives in a **runtime overlay**: three public web files
plus `brand.json` for the backend's report branding (ADR-054). Private report assets use the
separate mount described below.

| File          | Purpose                                                            |
| ------------- | ------------------------------------------------------------------ |
| `brand.js`    | Sets `window.__FLRC_BRAND__` before the app starts; see the format |
| `logo.svg`    | The logo on every screen and every report card                     |
| `favicon.svg` | The browser tab icon                                               |
| `brand.json`  | `name` and `accentColor` for the API's report cards                |

`brand.js` is plain, dependency-free JavaScript. Copy the generated
`apps/teacher/public/branding/brand.js` and change the strings:

```js
(function () {
  var here = document.currentScript && document.currentScript.src;
  window.__FLRC_BRAND__ = {
    name: "Deutsche Schule Istanbul",
    shortName: "DS Istanbul",
    accentColor: "#1c62b6",
    logoUrl: here ? new URL("logo.svg", here).href : null,
  };
  document.title = window.__FLRC_BRAND__.shortName;
})();
```

Mount the folder read-only at `/srv/branding` in the `flrc-web` container and at the
path named by `SCHOOL_BRANDING_DIR` in the API and worker containers. Files missing
from the overlay fall back to the generic ones baked into the image. The public demo
serves the generic overlay from each app's `public/branding/`.

Do not edit the written files by hand; the next `pnpm brand` overwrites them.

---

## Selling this to a school

A full rebrand, start to finish:

```bash
cp ~/their-logo.svg branding/logo.svg      # 1. their logo
$EDITOR branding/brand.json                 # 2. their name and colour
pnpm brand                                  # 3. apply
pnpm dev                                    # 4. look at it
```

Nothing else in the repository mentions a school name or a brand colour, so there
is no second place to remember and nothing to miss in a demo.

### Per-deployment overrides

If one codebase has to serve more than one school, the backend accepts
environment variables that win over this folder:

- `SCHOOL_NAME`: overrides `name` on printed report cards
- `SCHOOL_LOGO_PATH`: absolute path to a logo elsewhere on disk

The frontend reads the runtime overlay described above; separate schools can share the same
published images. Leave these two overrides unset when using the branding folder.

## Private report overlays and teacher signatures (ADR-057)

School-specific report templates, principal identities, and assets belong in the **private school
repository**, under `branding/reports/`. They are never copied into this repository or the web apps.
`SCHOOL_BRANDING_DIR` on both API and worker points to the complete private branding folder.
Teacher report names and PNG signatures belong to their `users` records and are edited in Admin →
Teachers → Report name & signature. Existing class assignments select the signers for each report.

An optional `reports/config.json` uses this structure:

```json
{
  "version": 1,
  "templates": { "german_karne": "karne.html", "french_karne": "karne.html" },
  "principals": {
    "primary": {
      "name": "Primary Principal",
      "titles": { "en": "Principal" },
      "signature": "principals/primary.png"
    },
    "middle": {
      "name": "Middle Principal",
      "titles": { "en": "Principal" },
      "signature": "principals/middle.png"
    }
  },
  "assets": { "german_cover": "covers/german-preview.png" },
  "covers": { "german_karne": "covers/german.pdf", "french_karne": "covers/french.pdf" }
}
```

Templates live in `reports/templates/`, may extend the built-in `base.html`, and receive the
existing report context plus `report_branding.principals` and `report_branding.assets`. Images are
resolved to data URIs. Each `card.teachers` item has a name, role list, user id, and optional
signature data URI. A missing signature is blank; the system never generates one. All paths are
relative to `reports/`, with traversal and escaping symlinks rejected. Missing or invalid configured
assets fail rather than silently dropping a principal or substituting an unrelated cover.

German/French templates with PDF covers must produce exactly two landscape A4 pages per student.
The first is the report face; the second is the preview cover, replaced with the original PDF page
in the final document. Grade-specific criteria and saved values still come from configured database
columns, not from positional guesses in a Word reference. Grades 1-4 select the primary principal;
grades 5-8 select the middle principal.

For a school with private report assets, create `branding/public/` containing **only** the public
`brand.js`, `logo.svg`, and `favicon.svg`, and change the web volume to
`./branding/public:/srv/branding:ro`. Keep API/worker volumes as `./branding:/srv/branding:ro`.
This separate mount is required even when using older web images; newer Caddy configurations also
allowlist the three public files. Never copy report assets into a frontend `public/` folder.

Teacher signatures and identity audit records are included in database backups. Principal assets
and templates are maintained in the private deployment repository. Restart the API and worker after
an overlay change. Publish a release containing migration `e2a91c743b60` and upgrade both images
before using the overlay; do not pin an image tag that has not been published.

## Verification and current programme changes

Relevant handbook steps: 1.10 and 4.2; repository review date: 2026-09-11. After changing source
branding, run `pnpm brand`, `pnpm brand:check`, and `pnpm brand:test` from the application root.
For a private runtime overlay, verify both authorized report rendering and denial of public
access to `reports/` assets. A database backup alone does not recover private templates/principals.

The pending ADR-063 removes grades 5-8 English teacher comments from new report generation while
preserving underlying grade/audit history. Primary English and German/French retain comments.
The PDF batching change must preserve duplex ordering and cover replacement for private layouts.
Check these against synthetic data after upgrading to a release that actually contains the changes;
existing 1.2.0 pins and already-downloaded reports do not change when this README is edited.
