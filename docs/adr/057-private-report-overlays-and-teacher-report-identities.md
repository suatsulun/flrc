# ADR-057: Private report overlays and teacher report identities

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-09-09

**Phase:** 3 (teacher administration), 4.2 (reports)

## Context

Schools need their own report layouts, original PDF back covers, and different principals for
primary and middle grades. Teacher names and signatures must follow class assignments. The public
application and demo must remain generic, and private signature assets must not be served as
unauthenticated branding files.

## Decision

Add nullable `report_name`, deferred `signature_png` (PostgreSQL bytea), and `signature_digest`
columns to the existing `users` identity. The account name remains the fallback when report_name
is empty. Reuse `teaching_assignments` to gather the subject's teachers once per report set;
English main and skills roles assigned to one person produce one signer with both role labels.
No student fields, grade values, authorizations or assignment rules change.

A separate `report_identity_audits` table records the actor, target, old/new report name and old/new
PNG digest in the same transaction. The grade-specific audit table requires student and column
foreign keys and cannot represent this administrative event. Image bytes are never duplicated in
this audit. Audits follow the target account's retention and keep a nullable actor reference.

The admin teacher screen edits the printed name and uploads, previews, replaces or deletes the PNG
through admin-only, same-origin routes. Validate PNG structure, checksums, one frame, at most 1 MiB,
4 million pixels and 4096 pixels per side, then re-encode without metadata. Pillow is already a
WeasyPrint dependency and is now declared directly. Storage stays in the existing school database
and its encrypted backups; no filesystem upload store or new processor is introduced. The public
demo's temporary visitor accounts cannot acquire report identities.

`SCHOOL_BRANDING_DIR/reports/config.json` is an optional versioned private overlay. It chooses
Jinja HTML templates, image assets, original German/French back-cover PDFs, and principal identities
for `primary` (grades 1-4) and `middle` (5-8). Templates use a sandbox with automatic HTML escaping;
asset paths must remain inside the report folder. WeasyPrint continues to allow only data URIs.
PDF covers replace duplex back pages, retaining the original cover content. Invalid cover size or
page count fails explicitly. Default templates and public branding retain their existing appearance.

School deployment repositories keep real names, artwork and templates under their private branding
folder and mount only a generated `branding/public/` directory into the web service. The shared
Caddy configuration additionally serves only `brand.js`, `logo.svg`, and `favicon.svg` under either
branding URL. Template/identity changes affect newly generated reports; existing exported PDFs
remain unchanged. School identity caches reload on API/worker restart.

## Validation and deployment

Migration `e2a91c743b60` follows the existing head and preserves accounts. Tests cover upgrade and
rollback, PNG validation and metadata stripping, authorization and origin checks, identity auditing,
assigned-teacher selection and deduplication, principal selection, sandbox/path boundaries, duplex
cover replacement and generic fallback. Both application images must be released and upgraded
together before a school's overlay can use the feature. Editing repository configuration does not
apply a production migration or publish a release.
