#!/usr/bin/env node

import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const LOCALES = ["en", "tr", "de", "fr"];
const LOCALE_DIR = join(ROOT, "packages/i18n/src/locales");
const SOURCE_ROOTS = ["apps/admin/src", "apps/teacher/src", "packages/ui/src"];

function flatten(value, prefix = "", output = []) {
  for (const [key, child] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (child && typeof child === "object" && !Array.isArray(child)) {
      flatten(child, path, output);
    } else {
      output.push(path);
    }
  }
  return output;
}

function duplicateFormattedKeys(source, locale) {
  const parents = [];
  const seen = new Set();
  const duplicates = [];
  for (const line of source.split("\n")) {
    const match = /^(\s*)"([^"]+)"\s*:/.exec(line);
    if (!match) continue;
    const level = match[1].length / 2;
    parents.length = Math.max(0, level - 1);
    const path = [...parents, match[2]].join(".");
    if (seen.has(path)) duplicates.push(`${locale}:${path}`);
    seen.add(path);
    if (/\{\s*,?\s*$/.test(line)) parents[level - 1] = match[2];
  }
  return duplicates;
}

function sourceFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx)$/.test(entry.name) ? [path] : [];
  });
}

const resources = {};
const errors = [];
for (const locale of LOCALES) {
  const path = join(LOCALE_DIR, `${locale}.json`);
  const source = readFileSync(path, "utf8");
  errors.push(...duplicateFormattedKeys(source, locale).map((key) => `duplicate key ${key}`));
  resources[locale] = new Set(flatten(JSON.parse(source)));
}

for (const locale of LOCALES.slice(1)) {
  for (const key of resources.en) {
    if (!resources[locale].has(key)) errors.push(`${locale} is missing ${key}`);
  }
  for (const key of resources[locale]) {
    if (!resources.en.has(key)) errors.push(`${locale} has an extra key ${key}`);
  }
}

const used = new Map();
const literalPattern = /\bt\s*\(\s*(?:"([^"]+)"|'([^']+)'|`([^`$]+)`)/g;
for (const root of SOURCE_ROOTS) {
  for (const file of sourceFiles(join(ROOT, root))) {
    const source = readFileSync(file, "utf8");
    for (const match of source.matchAll(literalPattern)) {
      const key = match[1] ?? match[2] ?? match[3];
      if (!used.has(key)) used.set(key, []);
      used.get(key).push(relative(ROOT, file));
    }
  }
}

const requiredDynamicKeys = [
  ...["english", "german", "french"].map((value) => `subjects.${value}`),
  ...["main", "skills", "german", "french"].map((value) => `roles.${value}`),
  ...["primary", "middle"].map((value) => `teachingStages.${value}`),
  ...["setup", "active", "archived", "open", "locked"].map((value) => `lifecycle.${value}`),
  ...["all", "primary", "middle", "german", "french"].map(
    (value) => `assignmentBoard.filters.${value}`,
  ),
  ...["score", "scale3", "text"].map((value) => `columns.valueTypes.${value}`),
  ...[
    "wrong_domain",
    "not_registered",
    "google_error",
    "email_not_verified",
    "invalid_identity",
    "identity_mismatch",
  ].map((value) => `auth.errors.${value}`),
  ...["students", "classes", "teachers", "grants", "saves", "missingAssignments"].map(
    (value) => `coordinator.${value}`,
  ),
  ...[
    "new_students",
    "assigned_numbers",
    "placed_students",
    "renamed_students",
    "new_classes",
    "new_enrollments",
    "moved_students",
    "language_changes",
    "unchanged",
  ].map((value) => `import.counts.${value}`),
  ...[
    "english_elementary",
    "english_middle",
    "german_karne",
    "french_karne",
    "progress_pdf",
    "year_export",
  ].map((value) => `reports.kinds.${value}`),
  ...["english_elementary", "english_middle", "german_karne", "french_karne"].flatMap((value) => [
    `reports.setScopes.${value}`,
    `reports.setDescriptions.${value}`,
  ]),
  ...["queued", "running", "succeeded", "failed"].map((value) => `reports.status.${value}`),
];

for (const key of [...used.keys(), ...requiredDynamicKeys]) {
  for (const locale of LOCALES) {
    if (!resources[locale].has(key)) {
      const files = used.get(key)?.join(", ");
      errors.push(`${locale} is missing used key ${key}${files ? ` (${files})` : ""}`);
    }
  }
}

if (errors.length) {
  console.error(`Translation integrity failed with ${errors.length} issue(s):`);
  for (const error of [...new Set(errors)].sort()) console.error(`- ${error}`);
  process.exit(1);
}

console.log(
  `Translation integrity passed: ${resources.en.size} keys across ${LOCALES.length} locales; ${used.size} literal UI keys checked.`,
);
