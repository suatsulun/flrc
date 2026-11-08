# ADR-040: UI palette decoupled from the school accent colour

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-08-21
**Phase:** 4.x

## Context

The whole UI palette derived its hue from the school's accent colour: `pnpm brand` converted
`branding/brand.json` (`#2f7168`) to `--brand-hue: 183.3` and every brand-family token rotated with
it, over green-tinted slate backgrounds. With a teal school colour, the apps read as mossy green,
and any future school colour would recolour every surface of the product, for better or worse.

## Decision

The design tokens in `packages/ui/src/styles/theme.css` no longer consume `--brand-hue`. The UI
uses two fixed, contrast-checked palettes chosen from a twenty-option ballot: light "Parchment"
(warm paper ground, slate-brown ink, navy action colour) and dark "Graphite" (lifted neutral
charcoal, light-key buttons, steel-blue focus ring as the only hue). The school's colour remains
where branding belongs: the logo, the printed report cards, and the `theme-color` meta that
`pnpm brand` still writes. `branding/generated/brand.css` keeps publishing `--brand-hue` so the
branding pipeline is unchanged, even though the UI ignores it.

## Alternatives considered

- Keep the hue rotation but tune lightness/chroma: this still recolours the whole UI per school and
  cannot make a teal brand look neutral.
- Rotate only action colours (buttons, links) with the brand: rejected for now; it can be
  revisited by pointing `--primary` back at a brand-derived value.

## Consequences

- Dark mode is neutral charcoal instead of green slate; light mode is warm paper with navy ink.
- Rebranding no longer changes the app's surfaces, only the logo, report cards, and browser chrome.
- The comment in generated `brand.css` claiming theme.css reads its hue is stale until
  `scripts/branding.mjs` is next touched.
