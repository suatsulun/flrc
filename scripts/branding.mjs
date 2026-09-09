#!/usr/bin/env node
/**
 * Applies the contents of `branding/` to every place that needs it.
 *
 *   pnpm brand          write the derived files
 *   pnpm brand --check  verify they are up to date (used by CI)
 *
 * `branding/brand.json` and `branding/logo.svg` are the single source of truth.
 * Most consumers read them directly — the web apps import `@flrc/branding` — but
 * three kinds of consumer cannot, and this script feeds those:
 *
 *   1. `index.html`, which is not JavaScript and cannot import a module.
 *   2. The CSS palette, which needs the accent hue as a literal number.
 *   3. The Python backend, which renders report cards and cannot read the repo
 *      root (the Docker image only copies `src/`).
 *   4. The runtime overlay, `public/branding/` in each app: a blocking
 *      `brand.js` plus the logo and favicon. A deployment mounts a school's own
 *      copy of that folder over the generic one and never rebuilds (ADR-054).
 *
 * Everything it writes is committed, so a fresh clone works without running it.
 * `predev` and `prebuild` run it automatically, and `--check` fails CI if a
 * derived file drifts from `branding/`.
 */

import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const BRANDING = join(ROOT, "branding");
const CHECK = process.argv.includes("--check");

const paint = (code) => (text) => `\u001b[${code}m${text}\u001b[0m`;
const red = paint(31);
const green = paint(32);
const dim = paint(2);
const bold = paint(1);

function fail(message, hint) {
  console.error(`${red("✗")} ${message}`);
  if (hint) console.error(`  ${dim(hint)}`);
  process.exit(1);
}

/* ── Colour maths ──────────────────────────────────────────────────────────────
 * The UI palette keeps a fixed, contrast-checked lightness and chroma and takes
 * only the *hue* from the school's colour. That way any school colour produces a
 * palette that still clears 4.5:1 for white-on-primary — which picking arbitrary
 * lightness never guarantees. Formulae: Björn Ottosson's OKLab.
 */

const toLinear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const toGamma = (c) => (c <= 0.0031308 ? c * 12.92 : 1.055 * c ** (1 / 2.4) - 0.055);

function hexToOklch(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => toLinear(parseInt(hex.slice(i, i + 2), 16) / 255));
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  const hue = (Math.atan2(B, A) * 180) / Math.PI;
  return { L, C: Math.hypot(A, B), h: (hue + 360) % 360 };
}

function oklchToHex(L, C, hueDegrees) {
  const rad = (hueDegrees * Math.PI) / 180;
  const A = C * Math.cos(rad);
  const B = C * Math.sin(rad);
  const l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3;
  const m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3;
  const s = (L - 0.0894841775 * A - 1.291485548 * B) ** 3;
  const channels = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
  return `#${channels
    .map((c) => Math.round(Math.min(Math.max(toGamma(c), 0), 1) * 255))
    .map((c) => c.toString(16).padStart(2, "0"))
    .join("")}`;
}

/** Relative luminance, for the contrast note printed at the end. */
function contrastWithWhite(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => toLinear(parseInt(hex.slice(i, i + 2), 16) / 255));
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return (1.05 / (luminance + 0.05)).toFixed(2);
}

/* ── Read and validate branding/ ────────────────────────────────────────────── */

const brandPath = join(BRANDING, "brand.json");
if (!existsSync(brandPath)) fail(`Missing ${relative(ROOT, brandPath)}`, "See branding/README.md.");

let brand;
try {
  brand = JSON.parse(readFileSync(brandPath, "utf8"));
} catch (error) {
  fail(`${relative(ROOT, brandPath)} is not valid JSON`, error.message);
}

if (typeof brand.name !== "string" || !brand.name.trim())
  fail('brand.json needs a non-empty "name"', 'e.g. "name": "Deutsche Schule Istanbul"');
if (brand.shortName !== undefined && typeof brand.shortName !== "string")
  fail('brand.json "shortName" must be a string if present');
if (!/^#[0-9a-fA-F]{6}$/.test(brand.accentColor ?? ""))
  fail('brand.json needs "accentColor" as a 6-digit hex', 'e.g. "accentColor": "#2c5fcb"');

const logoPath = join(BRANDING, "logo.svg");
if (!existsSync(logoPath))
  fail(`Missing ${relative(ROOT, logoPath)}`, "Drop the school logo here.");

// The favicon is optional; the logo stands in when it is absent.
const faviconSource = existsSync(join(BRANDING, "favicon.svg"))
  ? join(BRANDING, "favicon.svg")
  : logoPath;

const shortName = (brand.shortName || brand.name).trim();
const hue = Math.round(hexToOklch(brand.accentColor).h * 10) / 10;

// Must match the token definitions in packages/ui/src/styles/theme.css.
const primaryHex = oklchToHex(0.5, 0.15, hue);

/* ── Derived files ─────────────────────────────────────────────────────────── */

/** Rewrites one attribute of a self-closing tag, leaving the rest untouched. */
function setHtmlAttribute(html, pattern, replacement) {
  if (!pattern.test(html)) fail(`Could not find ${pattern} to update`);
  return html.replace(pattern, replacement);
}

function brandedHtml(appPath) {
  let html = readFileSync(join(ROOT, appPath), "utf8");
  html = setHtmlAttribute(
    html,
    /<meta name="theme-color" content="[^"]*" \/>/,
    `<meta name="theme-color" content="${primaryHex}" />`,
  );
  html = setHtmlAttribute(html, /<title>[^<]*<\/title>/, `<title>${shortName}</title>`);
  return html;
}

const brandScript = `/*
 * Generated by \`pnpm brand\` from branding/brand.json — do not edit by hand.
 *
 * Runs before the app (a blocking script in index.html) and publishes the
 * school's identity for the runtime. A deployment overrides this folder to
 * rebrand without a rebuild: see branding/README.md.
 */
(function () {
  var here = document.currentScript && document.currentScript.src;
  var brand = {
    name: ${JSON.stringify(brand.name.trim())},
    shortName: ${JSON.stringify(shortName)},
    accentColor: ${JSON.stringify(brand.accentColor.toLowerCase())},
    logoUrl: here ? new URL("logo.svg", here).href : null,
  };
  window.__FLRC_BRAND__ = brand;
  document.title = brand.shortName;
})();
`;

const outputs = [
  {
    path: "branding/generated/brand.css",
    contents: `/*
 * Generated by \`pnpm brand\` from branding/brand.json — do not edit by hand.
 *
 * The whole UI palette is one hue rotation away from the school's colour:
 * theme.css keeps the contrast-checked lightness and chroma and reads the hue
 * from here. Accent colour ${brand.accentColor} → hue ${hue}deg → primary ${primaryHex}.
 */
:root {
  --brand-hue: ${hue};
}
`,
  },
  {
    path: "apps/backend/src/flrc/modules/reports/assets/brand.json",
    contents: `${JSON.stringify(
      {
        _generated: "Written by `pnpm brand` from branding/brand.json — do not edit by hand.",
        name: brand.name.trim(),
        accentColor: brand.accentColor.toLowerCase(),
      },
      null,
      2,
    )}\n`,
  },
  ...["teacher", "admin"].flatMap((app) => [
    { path: `apps/${app}/public/branding/brand.js`, contents: brandScript },
    { path: `apps/${app}/public/branding/logo.svg`, copyFrom: logoPath },
    { path: `apps/${app}/public/branding/favicon.svg`, copyFrom: faviconSource },
  ]),
  { path: "apps/backend/src/flrc/modules/reports/assets/logo.svg", copyFrom: logoPath },
  { path: "apps/teacher/index.html", contents: brandedHtml("apps/teacher/index.html") },
  { path: "apps/admin/index.html", contents: brandedHtml("apps/admin/index.html") },
];

/* ── Apply or verify ───────────────────────────────────────────────────────── */

const stale = [];
const written = [];

for (const output of outputs) {
  const target = join(ROOT, output.path);
  const next = output.copyFrom ? readFileSync(output.copyFrom) : Buffer.from(output.contents);
  const current = existsSync(target) ? readFileSync(target) : null;

  if (current && current.equals(next)) continue;
  if (CHECK) {
    stale.push(output.path);
    continue;
  }
  mkdirSync(dirname(target), { recursive: true });
  if (output.copyFrom) copyFileSync(output.copyFrom, target);
  else writeFileSync(target, output.contents);
  written.push(output.path);
}

if (CHECK) {
  if (stale.length) {
    console.error(`${red("✗")} branding is out of date in ${stale.length} file(s):`);
    for (const path of stale) console.error(`    ${path}`);
    console.error(`\n  ${dim("Run `pnpm brand` and commit the result.")}`);
    process.exit(1);
  }
  console.log(`${green("✓")} branding is up to date`);
  process.exit(0);
}

console.log(`${bold(brand.name)}${shortName === brand.name ? "" : dim(`  (${shortName})`)}`);
console.log(
  `${dim("accent")} ${brand.accentColor} ${dim("→ hue")} ${hue}° ${dim("→ primary")} ${primaryHex} ` +
    `${dim(`(${contrastWithWhite(primaryHex)}:1 on white)`)}`,
);
console.log(
  written.length
    ? `${green("✓")} updated ${written.length} file(s):\n${written.map((p) => `    ${p}`).join("\n")}`
    : `${green("✓")} already up to date`,
);
