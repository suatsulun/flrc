import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  copyFileSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";

const html = '<meta name="theme-color" content="#000000" /><title>Old name</title>\n';
const logo = '<svg xmlns="http://www.w3.org/2000/svg"><title>Örnek</title></svg>\n';
const cssPath = "branding/generated/brand.css";

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), "flrc-branding-test-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const path = (relative) => join(root, relative);
  function write(relative, contents) {
    mkdirSync(dirname(path(relative)), { recursive: true });
    writeFileSync(path(relative), contents);
  }
  write("branding/brand.json", JSON.stringify({ name: "Test School", accentColor: "#1682bd" }));
  write("branding/logo.svg", logo);
  write("apps/teacher/index.html", html);
  write("apps/admin/index.html", html);
  mkdirSync(path("scripts"));
  copyFileSync(new URL("./branding.mjs", import.meta.url), path("scripts/branding.mjs"));
  return {
    root,
    path,
    write,
    read: (relative) => readFileSync(path(relative), "utf8"),
    run: (args = [], nodeArgs = []) =>
      spawnSync(process.execPath, [...nodeArgs, path("scripts/branding.mjs"), ...args], {
        cwd: root,
        encoding: "utf8",
      }),
  };
}

function succeeds(result) {
  assert.equal(result.status, 0, result.stderr || result.error?.message);
}

test("creates outputs, falls back to the logo, and leaves matching files untouched", (t) => {
  const f = fixture(t);
  succeeds(f.run());
  assert.match(f.read("apps/teacher/index.html"), /<title>Test School<\/title>/);
  assert.equal(f.read("apps/admin/public/branding/favicon.svg"), logo);
  assert.equal(f.read("apps/backend/src/flrc/modules/reports/assets/logo.svg"), logo);
  const before = statSync(f.path(cssPath));
  succeeds(f.run());
  succeeds(f.run(["--check"]));
  const after = statSync(f.path(cssPath));
  assert.equal(after.ino, before.ino);
  assert.equal(after.mtimeMs, before.mtimeMs);
  assert.ok(
    !readdirSync(f.root, { recursive: true }).some((name) => name.includes(".flrc-brand-")),
  );
});

test("uses a separate favicon when provided", (t) => {
  const f = fixture(t);
  const favicon = '<svg xmlns="http://www.w3.org/2000/svg"><title>Favicon</title></svg>';
  f.write("branding/favicon.svg", favicon);
  succeeds(f.run());
  for (const app of ["admin", "teacher"]) {
    assert.equal(f.read(`apps/${app}/public/branding/favicon.svg`), favicon);
    assert.equal(f.read(`apps/${app}/public/branding/logo.svg`), logo);
  }
});

test("check mode reports missing and stale files without writing", (t) => {
  const f = fixture(t);
  const missing = f.run(["--check"]);
  assert.equal(missing.status, 1);
  assert.match(missing.stderr, /branding is out of date/);
  assert.throws(() => statSync(f.path(cssPath)), { code: "ENOENT" });
  assert.equal(f.read("apps/admin/index.html"), html);
  succeeds(f.run());
  f.write(cssPath, "stale");
  assert.equal(f.run(["--check"]).status, 1);
  assert.equal(f.read(cssPath), "stale");
  succeeds(f.run());
  succeeds(f.run(["--check"]));
});

for (const target of [cssPath, "apps/admin/public/branding/logo.svg", "apps/teacher/index.html"]) {
  test(`replaces a symlink at ${target} without modifying its destination`, (t) => {
    const f = fixture(t);
    succeeds(f.run());
    f.write("unrelated.txt", target.endsWith(".html") ? html : "unrelated data");
    const original = f.read("unrelated.txt");
    rmSync(f.path(target));
    symlinkSync(f.path("unrelated.txt"), f.path(target));
    succeeds(f.run());
    assert.equal(f.read("unrelated.txt"), original);
    assert.ok(lstatSync(f.path(target)).isFile());
    succeeds(f.run(["--check"]));
  });
}

test("does not follow a symlink swapped in after reading an output", (t) => {
  const f = fixture(t);
  succeeds(f.run());
  f.write(cssPath, "stale");
  f.write("unrelated.txt", "unrelated data");
  // Inject the swap at the filesystem boundary so the race is deterministic.
  f.write(
    "swap.mjs",
    `import fs from "node:fs";
import { syncBuiltinESMExports } from "node:module";
const originalRead = fs.readFileSync;
fs.readFileSync = function (path, ...args) {
  const contents = originalRead(path, ...args);
  if (path === ${JSON.stringify(f.path(cssPath))}) {
    fs.unlinkSync(path);
    fs.symlinkSync(${JSON.stringify(f.path("unrelated.txt"))}, path);
  }
  return contents;
};
syncBuiltinESMExports();
`,
  );
  succeeds(f.run([], ["--import", f.path("swap.mjs")]));
  assert.equal(f.read("unrelated.txt"), "unrelated data");
  assert.ok(lstatSync(f.path(cssPath)).isFile());
  succeeds(f.run(["--check"]));
});

test("only missing files are treated as absent", (t) => {
  const f = fixture(t);
  mkdirSync(f.path("branding/favicon.svg"));
  const result = f.run();
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /EISDIR/);
});

for (const source of ["brand.json", "logo.svg"]) {
  test(`keeps the actionable diagnostic for missing ${source}`, (t) => {
    const f = fixture(t);
    rmSync(f.path(`branding/${source}`));
    const result = f.run();
    assert.equal(result.status, 1);
    assert.ok(result.stderr.includes(`Missing branding/${source}`));
  });
}
