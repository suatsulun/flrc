import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import type { ImportPreview, MeOut, YearOut } from "../packages/api-client/src/index";

import { adminOrigin as adminUrl } from "./helpers/origins";
const names = JSON.parse(
  execFileSync("apps/backend/.venv/bin/python", [
    "-c",
    "import json; from faker import Faker; f=Faker('tr_TR'); f.seed_instance(81); print(json.dumps([f.name() for _ in range(3)]))",
  ]).toString(),
) as string[];
const preview: ImportPreview = {
  sha256: "a".repeat(64),
  review_sha256: "b".repeat(64),
  counts: { unchanged: 1, moved_students: 1, new_students: 1 },
  issues: [],
  total_rows: 3,
  filtered_rows: 3,
  next_offset: null,
  classes: [
    { grade_level: 4, section: "A", count: 3 },
    { grade_level: 4, section: "B", count: 0 },
  ],
  class_moves: [],
  rows: names.map((full_name, i) => ({
    row: {
      school_number: i + 1,
      full_name,
      grade_level: 4,
      section: "A",
      language: i === 0 ? null : i === 1 ? "german" : "french",
      language_present: true,
      sheet: "4-A",
      row_number: i + 5,
    },
    actions:
      i === 0
        ? ["unchanged"]
        : i === 1
          ? ["class_changed", "language_edited"]
          : ["manual_added", "new_student", "new_enrollment"],
    original_class: i === 1 ? "4/B" : "4/A",
  })),
};

for (const size of [
  { width: 1920, height: 1080, theme: "dark", locale: "en" },
  { width: 1536, height: 864, theme: "dark", locale: "en" },
  { width: 1280, height: 900, theme: "light", locale: "de" },
  { width: 640, height: 900, theme: "light", locale: "fr" },
  { width: 390, height: 844, theme: "dark", locale: "tr" },
]) {
  test(`import cells fit and align at ${size.width}px in ${size.locale}`, async ({
    page,
  }, testInfo) => {
    const labels = JSON.parse(
      readFileSync(`packages/i18n/src/locales/${size.locale}.json`, "utf8"),
    ) as { import: Record<string, string>; students: Record<string, string> };
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.addInitScript(({ theme, locale }) => {
      localStorage.setItem("flrc-theme", theme);
      localStorage.setItem("i18nextLng", locale);
    }, size);
    // Layout fixtures stay entirely in this browser context and never touch a school database.
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/me")
        return route.fulfill({
          json: {
            id: 1,
            full_name: "Synthetic Admin",
            email: "admin@example.test",
            is_admin: true,
            is_coordinator: false,
            assignments: [],
          } satisfies MeOut,
        });
      if (path === "/api/admin/years")
        return route.fulfill({
          json: [
            {
              id: 1,
              label: "2027–2028",
              status: "setup",
              semesters: [],
              missing_school_numbers: 0,
            },
          ] satisfies YearOut[],
        });
      if (path === "/api/admin/import/dry-run") return route.fulfill({ json: preview });
      return route.abort();
    });
    await page.goto(`${adminUrl}/admin/import`);
    await page.getByLabel(labels.import.file, { exact: true }).setInputFiles({
      name: "synthetic-layout.xlsx",
      mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      buffer: Buffer.from("synthetic layout fixture"),
    });
    await page.getByRole("button", { name: labels.import.preview, exact: true }).click();
    const rows = page.getByTestId("import-student-row");
    await expect(rows).toHaveCount(3);
    const surface = page.getByTestId("import-roster-surface");
    await surface.scrollIntoViewIfNeeded();
    await page.evaluate(() => document.fonts.ready);
    const layout = await surface.evaluate((element, expected) => {
      const headers = Array.from(element.querySelectorAll("thead th"));
      const actionsIndex = headers.findIndex((h) => h.textContent?.trim() === expected.actions);
      const removeIndex = headers.findIndex(
        (h) => h.textContent?.trim() === expected.removeStudent,
      );
      const bodyRows = Array.from(element.querySelectorAll("tbody tr"));
      const mismatched = bodyRows.some((row) => {
        const cells = row.querySelectorAll("td");
        return (
          !cells[actionsIndex]?.querySelector('[data-slot="badge"]') ||
          !cells[removeIndex]?.querySelector("button")
        );
      });
      const overflowing = bodyRows.some((row) =>
        Array.from(row.querySelectorAll('[data-slot="badge"], select, button')).some((control) => {
          if (!control.getClientRects().length) return false;
          const cell = control.closest("td")!.getBoundingClientRect();
          const box = control.getBoundingClientRect();
          return box.left < cell.left - 1 || box.right > cell.right + 1;
        }),
      );
      const ghostArrows = Array.from(element.querySelectorAll("select")).some(
        (select) =>
          !select.getClientRects().length &&
          Boolean(select.parentElement?.querySelector("svg")?.getClientRects().length),
      );
      const clippedLabels = Array.from(element.querySelectorAll("select")).some((select) => {
        if (!select.getClientRects().length) return false;
        const style = getComputedStyle(select);
        const canvas = document.createElement("canvas");
        const context = canvas.getContext("2d")!;
        context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
        const available =
          select.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
        return context.measureText(select.selectedOptions[0].text).width > available + 1;
      });
      return { mismatched, overflowing, ghostArrows, clippedLabels };
    }, labels.import);
    expect(layout).toEqual({
      mismatched: false,
      overflowing: false,
      ghostArrows: false,
      clippedLabels: false,
    });
    await page.screenshot({ path: testInfo.outputPath("import-layout.png"), fullPage: true });
  });
}
