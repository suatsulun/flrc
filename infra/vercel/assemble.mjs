/**
 * Assemble the public demo web tier (ADR-064).
 *
 * The teacher build lands at the site root and the admin build under /admin,
 * the same layout the school Caddy image serves. Turborepo builds both apps
 * before this package because they are its dependencies (`^build`).
 */
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repository = resolve(here, "../..");
const output = join(here, "dist");
const builds = [
  { name: "@flrc/teacher", source: join(repository, "apps/teacher/dist"), target: output },
  {
    name: "@flrc/admin",
    source: join(repository, "apps/admin/dist"),
    target: join(output, "admin"),
  },
];

for (const build of builds) {
  if (!existsSync(join(build.source, "index.html"))) {
    throw new Error(
      `${build.name} has no build output at ${build.source}; ` +
        'run "pnpm turbo run build --filter=@flrc/demo-web" from the repository root',
    );
  }
}

rmSync(output, { recursive: true, force: true });
mkdirSync(output, { recursive: true });
for (const build of builds) {
  cpSync(build.source, build.target, { recursive: true });
}
cpSync(join(here, "static"), output, { recursive: true });

// The admin app must keep /admin/ as its asset base or its scripts 404 behind the rewrites.
const adminIndex = readFileSync(join(output, "admin", "index.html"), "utf8");
if (!adminIndex.includes('"/admin/assets/')) {
  throw new Error("the admin build does not reference /admin/assets/; check the Vite base path");
}

// Both panels live on one origin (ADR-022). A bundle that still links to a Vite
// development port would send demo visitors to localhost.
const leaks = [];
for (const file of walk(output)) {
  if (file.endsWith(".js") && /localhost:517[34]/.test(readFileSync(file, "utf8"))) {
    leaks.push(relative(output, file));
  }
}
if (leaks.length > 0) {
  throw new Error(
    "development hosts leaked into the demo bundle: " +
      leaks.join(", ") +
      ". Production builds default to /admin/ and /; unset VITE_ADMIN_URL and VITE_TEACHER_URL.",
  );
}

console.log(`assembled ${relative(repository, output)}: teacher at / and admin at /admin/`);

function* walk(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      yield* walk(path);
    } else {
      yield path;
    }
  }
}
