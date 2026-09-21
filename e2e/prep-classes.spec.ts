import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";
import { authenticatedContext } from "./helpers/auth";
import { adminOrigin } from "./helpers/origins";

test("Prep imports retain named classes through filtering, moves, undo and commit", async ({
  browser,
}) => {
  const context = await authenticatedContext(browser, "admin@example-school.k12.tr");
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const page = await context.newPage();
  await page.goto(`${adminOrigin}/admin/import`);
  const yearId = await page.getByLabel("Academic year", { exact: true }).inputValue();
  await page.getByLabel("Excel workbook", { exact: true }).setInputFiles({
    name: "synthetic-prep.xlsx",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: execFileSync("apps/backend/.venv/bin/python", [
      "e2e/fixtures/import-roster.py",
      "--prep",
    ]),
  });
  await page.getByRole("button", { name: "Preview changes", exact: true }).click();
  await expect(page.getByLabel("Browse grade", { exact: true })).toHaveValue("0");
  await expect(page.getByTestId("import-class-target").filter({ hasText: "Bulut" })).toBeVisible();
  const row = page.getByTestId("import-student-row").filter({ hasText: "Synthetic Prep 1" });
  const select = row.getByRole("combobox", { name: /^Class for / });
  await select.selectOption("0/Yıldız");
  await expect(select).toHaveValue("0/Yıldız");
  await page.getByRole("button", { name: "Undo change", exact: true }).click();
  await expect(select).toHaveValue("0/Bulut");
  await page.setViewportSize({ width: 390, height: 844 });
  await select.selectOption("0/Yıldız");
  await expect(select).toHaveValue("0/Yıldız");
  await page.getByRole("button", { name: "Commit import", exact: true }).click();
  await expect(page.getByRole("button", { name: "Commit import", exact: true })).toHaveCount(0);
  await page.goto(`${adminOrigin}/admin/classes`);
  await page.getByLabel("Academic year", { exact: true }).selectOption(yearId);
  await page.getByRole("radio", { name: "Prep", exact: true }).click();
  await page.getByRole("button", { name: /^Yıldız/ }).click();
  await expect(page.getByText("Synthetic Prep 1", { exact: true })).toBeVisible();
  await expect(page.getByText("Synthetic Prep 3", { exact: true })).toBeVisible();
  await context.close();
});
