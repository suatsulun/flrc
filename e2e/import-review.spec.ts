import { execFileSync } from "node:child_process";
import { expect } from "@playwright/test";
import type { AdminClassOut, RosterStudentOut } from "../packages/api-client/src/index";
import { test } from "./helpers/import-admin";

import { adminOrigin as adminUrl } from "./helpers/origins";
const fixture = () => ({
  name: "synthetic-review.xlsx",
  mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  buffer: execFileSync("apps/backend/.venv/bin/python", ["e2e/fixtures/import-roster.py"]),
});

test("import scrolls through the full roster, filters all rows, and commits reviewed class moves", async ({
  importContext: context,
}) => {
  test.setTimeout(60_000);
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const page = await context.newPage();
  await page.goto(`${adminUrl}/admin/import`);
  await page.getByLabel("Excel workbook", { exact: true }).setInputFiles(fixture());
  await page.getByRole("button", { name: "Preview changes", exact: true }).click();
  const rows = page.getByTestId("import-student-row");
  await expect(rows).toHaveCount(100);
  await expect(page.getByLabel("Browse grade", { exact: true })).toHaveValue("5");
  await expect(page.getByTestId("import-class-target")).toHaveCount(2);
  await page.getByTestId("import-scroll-sentinel").scrollIntoViewIfNeeded();
  await expect(rows).toHaveCount(200);
  await page.getByTestId("import-scroll-sentinel").scrollIntoViewIfNeeded();
  await expect(rows).toHaveCount(205);
  await expect(page.getByText("All 205 matching students loaded")).toBeVisible();

  await page.getByRole("textbox", { name: "Search name or school number" }).fill("İPEK IŞIK");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toHaveAttribute("data-row-key", "middle:78205");
  await page.getByRole("button", { name: "Clear filters", exact: true }).click();
  await page.getByLabel("Filter by grade", { exact: true }).selectOption("5");
  await page.getByLabel("Filter by class", { exact: true }).selectOption("5/B");
  await page.getByLabel("Second language", { exact: true }).selectOption("german");
  await expect(rows).toHaveCount(30);
  await page.getByRole("button", { name: "Clear filters", exact: true }).click();
  await page.getByLabel("Browse grade", { exact: true }).selectOption("5");
  await page.locator('[data-testid="import-class-target"][data-class="5/B"]').click();
  await expect(rows).toHaveCount(60);
  const movedRow = page.locator('[data-row-key="middle:78121"]');
  await movedRow
    .getByRole("button", { name: /^Drag / })
    .dragTo(page.locator('[data-testid="import-class-target"][data-class="5/A"]'));
  await expect(rows).toHaveCount(59);
  await expect(page.getByRole("button", { name: "Undo change", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Undo change", exact: true }).click();
  await expect(rows).toHaveCount(60);
  await movedRow.getByRole("combobox", { name: /^Class for / }).selectOption("5/A");
  await expect(rows).toHaveCount(59);
  await expect(page.getByText("1 class changes awaiting import")).toBeVisible();
  // A filtered preview still commits all students, including unloaded pages.
  await page.getByRole("button", { name: "Commit import", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Student import completed." })).toBeVisible();
  await expect(page.getByText(/205 students processed for/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Commit import", exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "Preview changes", exact: true }).click();
  await page.getByRole("textbox", { name: "Search name or school number" }).fill("78121");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Move class");
  // The original file says 5/B; the saved enrollment is now 5/A, so reimport would move it back.
  await expect(rows.first().getByRole("combobox", { name: /^Class for / })).toHaveValue("5/B");
});

test("changing file or year clears the review and mobile keeps a usable class selector", async ({
  importContext: context,
}) => {
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const page = await context.newPage();
  await page.goto(`${adminUrl}/admin/import`);
  await page.getByLabel("Excel workbook", { exact: true }).setInputFiles(fixture());
  await page.getByRole("button", { name: "Preview changes", exact: true }).click();
  await expect(page.getByTestId("import-student-row")).toHaveCount(100);
  const years = page.getByLabel("Academic year", { exact: true });
  const options = await years
    .locator("option")
    .evaluateAll((items) => items.map((item) => (item as HTMLOptionElement).value));
  const selected = await years.inputValue();
  await years.selectOption(options.find((value) => value !== selected)!);
  await expect(page.getByTestId("import-student-row")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Commit import", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Preview changes", exact: true }).click();
  await expect(page.getByTestId("import-student-row")).toHaveCount(100);
  await page.getByLabel("Excel workbook", { exact: true }).setInputFiles([]);
  await expect(page.getByTestId("import-student-row")).toHaveCount(0);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByLabel("Excel workbook", { exact: true }).setInputFiles(fixture());
  await page.getByRole("button", { name: "Preview changes", exact: true }).click();
  const row = page.getByTestId("import-student-row").first();
  await expect(row).toBeVisible();
  await row.getByRole("combobox", { name: /^Class for / }).selectOption("5/B");
  await expect(row.getByRole("combobox", { name: /^Class for / })).toHaveValue("5/B");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
    ),
  ).toBe(true);
  await row.scrollIntoViewIfNeeded();
  await page.screenshot({ path: "test-results/import-mobile.png" });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page
    .getByRole("textbox", { name: "Search name or school number" })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: "test-results/import-desktop.png" });
});

test("grade browsing filters the roster and additions, exclusions and language clearing survive commit", async ({
  importContext: context,
}) => {
  test.setTimeout(90_000);
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const page = await context.newPage();
  await page.goto(`${adminUrl}/admin/import`);
  const file = {
    ...fixture(),
    buffer: execFileSync("apps/backend/.venv/bin/python", [
      "e2e/fixtures/import-roster.py",
      "--grade-four",
    ]),
  };
  await page.getByLabel("Excel workbook", { exact: true }).setInputFiles(file);
  await page.getByRole("button", { name: "Preview changes", exact: true }).click();
  const rows = page.getByTestId("import-student-row");
  await expect(rows).toHaveCount(100);
  await page.getByLabel("Browse grade", { exact: true }).selectOption("4");
  await expect(page.getByLabel("Filter by grade", { exact: true })).toHaveValue("4");
  await expect(page.getByText(/of 180 matches/)).toBeVisible();
  await page.locator('[data-class="4/B"]').click();
  await expect(rows).toHaveCount(60);
  await page.getByLabel("Browse grade", { exact: true }).selectOption("4");
  await expect(page.getByLabel("Filter by class", { exact: true })).toHaveValue("");
  await expect(rows).toHaveCount(100);
  await page.getByTestId("import-scroll-sentinel").scrollIntoViewIfNeeded();
  await expect(rows).toHaveCount(180);
  const clearRow = page.locator('[data-row-key="primary:78001"]');
  await clearRow.getByRole("combobox", { name: /^Second language for / }).selectOption("");
  await expect(clearRow.getByRole("combobox", { name: /^Second language for / })).toHaveValue("");
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await expect(page.getByRole("button", { name: "Commit import", exact: true })).toBeDisabled();
  await form.getByRole("spinbutton", { name: "School number" }).fill("78999");
  await form.getByRole("textbox", { name: "Full name" }).fill("Synthetic Manual Addition");
  await form.getByLabel("New student’s class").selectOption("4/B");
  await form.getByLabel("Second language", { exact: true }).selectOption("german");
  await form.getByRole("button", { name: "Add student", exact: true }).click();
  await expect(rows).toHaveCount(61);
  await expect(page.locator('[data-row-key="primary:78999"]')).toContainText("Added in review");
  const excludeRow = page.locator('[data-row-key="primary:78121"]');
  await excludeRow.getByRole("button", { name: /^Exclude / }).click();
  await expect(rows).toHaveCount(60);
  await page.getByRole("button", { name: "Undo change", exact: true }).click();
  await expect(rows).toHaveCount(61);
  await excludeRow.getByRole("button", { name: /^Exclude / }).click();
  await expect(rows).toHaveCount(60);
  await page.getByRole("button", { name: "Commit import", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Student import completed." })).toBeVisible();
  await expect(page.getByText(/205 students processed for/)).toBeVisible();
  const yearId = await page.getByLabel("Academic year", { exact: true }).inputValue();
  const classesResponse = await page.request.get(`${adminUrl}/api/admin/years/${yearId}/classes`);
  expect(classesResponse.ok()).toBe(true);
  const classes = (await classesResponse.json()) as AdminClassOut[];
  const a = classes.find((c) => c.grade_level === 4 && c.section === "A")!;
  const b = classes.find((c) => c.grade_level === 4 && c.section === "B")!;
  const aRoster = (await (
    await page.request.get(`${adminUrl}/api/admin/classes/${a.id}/roster`)
  ).json()) as RosterStudentOut[];
  const bRoster = (await (
    await page.request.get(`${adminUrl}/api/admin/classes/${b.id}/roster`)
  ).json()) as RosterStudentOut[];
  expect(aRoster.find((s) => s.school_number === 78001)?.language).toBeNull();
  expect(bRoster.find((s) => s.school_number === 78999)?.language).toBe("german");
  expect(bRoster.some((s) => s.school_number === 78121)).toBe(false);
});

test("equal numbers in primary and middle school stay independent through edits and commit", async ({
  importContext: context,
}) => {
  test.setTimeout(60_000);
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const page = await context.newPage();
  await page.goto(`${adminUrl}/admin/import`);
  await page.getByLabel("Excel workbook", { exact: true }).setInputFiles({
    ...fixture(),
    buffer: execFileSync("apps/backend/.venv/bin/python", [
      "e2e/fixtures/import-roster.py",
      "--cross-stage",
    ]),
  });
  await page.getByRole("button", { name: "Preview changes", exact: true }).click();
  const rows = page.getByTestId("import-student-row");
  await expect(rows).toHaveCount(5);
  const primaryOne = page.locator('[data-row-key="primary:77001"]');
  const middleOne = page.locator('[data-row-key="middle:77001"]');
  const middleThree = page.locator('[data-row-key="middle:77003"]');
  await expect(primaryOne).toContainText("Synthetic Primary One");
  await expect(middleOne).toContainText("Synthetic Middle One");
  const language = /^Second language for /;
  const schoolClass = /^Class for /;

  await primaryOne.getByRole("combobox", { name: language }).selectOption("french");
  await expect(primaryOne.getByRole("combobox", { name: language })).toHaveValue("french");
  await expect(middleOne.getByRole("combobox", { name: language })).toHaveValue("german");

  await primaryOne.getByRole("combobox", { name: schoolClass }).selectOption("4/B");
  await expect(primaryOne.getByRole("combobox", { name: schoolClass })).toHaveValue("4/B");
  await expect(middleOne.getByRole("combobox", { name: schoolClass })).toHaveValue("5/A");
  // A move into the other stage keeps the row's source identity.
  await middleThree.getByRole("combobox", { name: schoolClass }).selectOption("4/A");
  await expect(middleThree.getByRole("combobox", { name: schoolClass })).toHaveValue("4/A");
  await expect(page.getByText("2 class changes awaiting import")).toBeVisible();

  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await form.getByRole("spinbutton", { name: "School number" }).fill("77004");
  await form.getByRole("textbox", { name: "Full name" }).fill("Synthetic Manual Primary");
  await form.getByLabel("New student’s class").selectOption("4/B");
  await form.getByRole("button", { name: "Add student", exact: true }).click();
  await page.getByRole("button", { name: "Clear filters", exact: true }).click();
  await expect(rows).toHaveCount(6);
  await expect(page.locator('[data-row-key="primary:77004"]')).toContainText("Added in review");

  await middleOne.getByRole("button", { name: /^Exclude / }).click();
  await expect(rows).toHaveCount(5);
  await expect(middleOne).toHaveCount(0);
  await expect(primaryOne.getByRole("combobox", { name: schoolClass })).toHaveValue("4/B");
  await expect(primaryOne.getByRole("combobox", { name: language })).toHaveValue("french");
  await expect(middleThree.getByRole("combobox", { name: schoolClass })).toHaveValue("4/A");

  await page.getByRole("button", { name: "Commit import", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Student import completed." })).toBeVisible();
  await expect(page.getByText(/\b5 students processed for/)).toBeVisible();
  const yearId = await page.getByLabel("Academic year", { exact: true }).inputValue();
  const classesResponse = await page.request.get(`${adminUrl}/api/admin/years/${yearId}/classes`);
  expect(classesResponse.ok()).toBe(true);
  const classes = (await classesResponse.json()) as AdminClassOut[];
  const roster = async (grade: number, section: string) => {
    const target = classes.find((c) => c.grade_level === grade && c.section === section);
    // A class whose only file rows were excluded or moved away may not have been created.
    if (!target) return [];
    const response = await page.request.get(`${adminUrl}/api/admin/classes/${target.id}/roster`);
    expect(response.ok()).toBe(true);
    return ((await response.json()) as RosterStudentOut[]).filter(
      (s) => s.school_number !== null && s.school_number >= 77001 && s.school_number <= 77004,
    );
  };
  const pick = ({ school_number, full_name, language }: RosterStudentOut) => ({
    school_number,
    full_name,
    language,
  });
  expect((await roster(4, "A")).map(pick)).toEqual([
    { school_number: 77003, full_name: "Synthetic Middle Three", language: "german" },
  ]);
  expect(
    (await roster(4, "B"))
      .map(pick)
      .sort((a, b) => (a.school_number ?? 0) - (b.school_number ?? 0)),
  ).toEqual([
    { school_number: 77001, full_name: "Synthetic Primary One", language: "french" },
    { school_number: 77002, full_name: "Synthetic Primary Two", language: "french" },
    { school_number: 77004, full_name: "Synthetic Manual Primary", language: null },
  ]);
  expect(await roster(5, "A")).toEqual([]);
  expect((await roster(5, "B")).map(pick)).toEqual([
    { school_number: 77002, full_name: "Synthetic Middle Two", language: "french" },
  ]);
});
