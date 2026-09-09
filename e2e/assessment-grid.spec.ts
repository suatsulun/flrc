import { mergeSavedGrid } from "../apps/teacher/src/grid/merge-saved-grid";
import type { DirtyCell } from "../apps/teacher/src/grid/dirty-store";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import type {
  ClassCatalogOut,
  GridOut,
  MeOut,
  SaveRequest,
  SaveResponse,
  YearOut,
} from "../packages/api-client/src/index";

import { teacherOrigin as teacherUrl } from "./helpers/origins";
const names = JSON.parse(
  execFileSync("apps/backend/.venv/bin/python", [
    "-c",
    "import json; from faker import Faker; f=Faker('tr_TR'); f.seed_instance(83); print(json.dumps([f.name() for _ in range(4)]))",
  ]).toString(),
) as string[];
const assessments: Array<[string, string | null, string]> = [
  ["Exam 1", "Exams", "score"],
  ["Exam 2", "Exams", "score"],
  ["Homework 1", "Homework", "score"],
  ["Homework 2", "Homework", "score"],
  [
    "Ders içi ve/veya ders dışı etkinliklere istekle ve aktif olarak katılır.",
    "Derse karşı tutumlar",
    "scale3",
  ],
  ["Ders materyallerini zamanında ve eksiksiz getirir.", "Derse karşı tutumlar", "scale3"],
  ["Verilen ödevleri/çalışma kâğıtlarını düzenli olarak yapar.", "Derse karşı tutumlar", "scale3"],
  ["Duyduğu basit yönergeleri anlayabilir.", "Dinleme anlama", "scale3"],
  ["Dinlediği kelimeleri tekrar edebilir.", "Dinleme anlama", "scale3"],
  ["Öğrenmiş olduğu sözcükleri yüksek sesle tekrar edebilir.", "Okuma anlama", "scale3"],
  ["Basit sözcüklerle resimleri eşleştirebilir.", "Okuma anlama", "scale3"],
  ["Günlük konularda basit konuşmaları başlatabilir.", "Konuşma", "scale3"],
  ["Kendini ve üçüncü kişileri basit cümlelerle tanıtabilir.", "Konuşma", "scale3"],
  ["Öğrendiği kelimeleri ve cümle kalıplarını yazabilir.", "Yazma", "scale3"],
  ["Teacher’s comments", null, "text"],
];

function fixture(grade = 6, owned = true): GridOut {
  return {
    meta: {
      class_id: 1,
      class_name: `${grade}/A`,
      grade_level: grade,
      subject: "german",
      year_id: 1,
      year_label: "Synthetic year",
      semester_id: 1,
      semester_number: 1,
      semester_status: "open",
      year_status: "active",
      my_grants: [],
      my_last_batch: null,
    },
    columns: assessments
      .map(([label, group, value_type], i) => ({
        id: i + 1,
        label,
        group,
        value_type,
        owner_role: "german",
        owner_name: "Synthetic Teacher",
        owned_by_you: owned,
        position: i + 1,
      }))
      .filter((c) => grade !== 4 || c.value_type === "scale3"),
    rows: names.map((full_name, i) => ({
      student_id: i + 1,
      school_number: 78001 + i,
      full_name,
      cells: {},
    })),
  };
}

async function mockGrid(
  page: Page,
  grid: GridOut,
  onSave?: (body: SaveRequest) => void | Promise<void>,
) {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/me")
      return route.fulfill({
        json: {
          id: 1,
          full_name: "Synthetic Teacher",
          email: "teacher@example.test",
          is_admin: true,
          is_coordinator: false,
          assignments: [],
        } satisfies MeOut,
      });
    if (path === "/api/academic-years")
      return route.fulfill({
        json: [
          {
            id: 1,
            label: "Synthetic year",
            status: "active",
            missing_school_numbers: 0,
            semesters: [{ id: 1, number: 1, status: "open" }],
          },
        ] satisfies YearOut[],
      });
    if (path === "/api/class-catalog")
      return route.fulfill({
        json: [
          {
            id: 1,
            name: grid.meta.class_name,
            grade_level: grid.meta.grade_level,
            section: "A",
            subjects: [
              {
                subject: "german",
                student_count: grid.rows.length,
                column_count: grid.columns.length,
                owner_roles: ["german"],
                my_roles: ["german"],
                can_write: true,
              },
            ],
          },
        ] satisfies ClassCatalogOut[],
      });
    if (path === "/api/classes/1/grid") return route.fulfill({ json: grid });
    if (path === "/api/classes/1/grid/save") {
      const body = route.request().postDataJSON() as SaveRequest;
      await onSave?.(body);
      return route.fulfill({
        json: {
          applied: body.cells.map((c) => ({
            student_id: c.student_id,
            column_id: c.column_id,
            version: c.expected_version + 1,
          })),
          conflicts: [],
          rejected: [],
        } satisfies SaveResponse,
      });
    }
    return route.abort();
  });
}

for (const size of [
  { width: 1920, height: 1080, theme: "dark", locale: "en" },
  { width: 1536, height: 864, theme: "dark", locale: "en" },
  { width: 1280, height: 900, theme: "light", locale: "tr" },
  { width: 768, height: 900, theme: "dark", locale: "fr" },
  { width: 390, height: 844, theme: "light", locale: "de" },
]) {
  test(`assessment headings are readable and all columns reachable at ${size.width}px`, async ({
    page,
  }, testInfo) => {
    const labels = JSON.parse(
      readFileSync(`packages/i18n/src/locales/${size.locale}.json`, "utf8"),
    ) as { grid: Record<string, string> };
    await page.setViewportSize(size);
    await page.addInitScript(({ theme, locale }) => {
      localStorage.setItem("flrc-theme", theme);
      localStorage.setItem("i18nextLng", locale);
    }, size);
    const grid = fixture(6, false);
    await mockGrid(page, grid);
    await page.goto(`${teacherUrl}/classes/1/german?semester=1`);
    await page.getByRole("radio", { name: labels.grid.gridView, exact: true }).click();
    const surface = page.getByTestId("grade-grid-surface");
    await expect(surface).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    const seen: string[] = [];
    for (let i = 0; i < grid.columns.length; i++) {
      const headings = page.getByTestId("assessment-heading");
      const texts = await headings.allTextContents();
      seen.push(...texts);
      expect(texts.length).toBeLessThanOrEqual(3);
      const dimensions = await headings.evaluateAll((elements) =>
        elements.map((element) => ({
          width: element.getBoundingClientRect().width,
          fontSize: parseFloat(getComputedStyle(element).fontSize),
          overflow: element.scrollWidth > element.clientWidth + 1,
          transform: getComputedStyle(element).textTransform,
        })),
      );
      for (const dimension of dimensions) {
        expect(dimension.fontSize).toBeGreaterThanOrEqual(14);
        expect(dimension.width).toBeGreaterThanOrEqual(size.width < 500 ? 160 : 200);
        expect(dimension.overflow).toBe(false);
        expect(dimension.transform).not.toBe("uppercase");
      }
      const next = page
        .getByRole("button", { name: labels.grid.nextAssessments, exact: true })
        .first();
      if (await next.isDisabled()) break;
      await next.click();
      await expect(headings.first()).not.toHaveText(texts[0]);
    }
    expect(seen).toEqual(grid.columns.map((c) => c.label));
    await page.getByRole("button", { name: "Derse karşı tutumlar 3", exact: true }).click();
    await expect(page.getByTestId("assessment-heading").first()).toHaveText(assessments[4][0]);
    await surface.scrollIntoViewIfNeeded();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await page.screenshot({
      path: testInfo.outputPath("readable-assessments.png"),
      fullPage: true,
    });
  });
}

test("drafts and keyboard navigation survive assessment paging and category changes", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1536, height: 864 });
  await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  let saved: SaveRequest | undefined;
  await mockGrid(page, fixture(), (body) => {
    saved = body;
  });
  await page.goto(`${teacherUrl}/classes/1/german?semester=1`);
  const first = page.getByTestId("cell-1-1").getByRole("textbox");
  await first.fill("82");
  await first.press("Enter");
  await expect(page.getByTestId("cell-2-1").getByRole("textbox")).toBeFocused();
  await page.getByRole("button", { name: "Next", exact: true }).first().click();
  await expect(first).toHaveCount(0);
  await page.getByRole("button", { name: "Previous", exact: true }).first().click();
  await expect(first).toHaveValue("82");
  await page.getByRole("button", { name: "Dinleme anlama 2", exact: true }).click();
  const scale = page.getByTestId("cell-1-8").getByRole("button");
  await scale.focus();
  await scale.press("2");
  await scale.press("ArrowRight");
  await expect(page.getByTestId("cell-1-9").getByRole("button")).toBeFocused();
  await page.getByRole("button", { name: "All assessments 15", exact: true }).click();
  await expect(first).toHaveValue("82");
  await page.getByTestId("save-grid").click();
  await expect.poll(() => saved?.cells.length).toBe(2);
  expect(saved?.cells).toEqual(
    expect.arrayContaining([
      { student_id: 1, column_id: 1, value: 82, expected_version: 0 },
      { student_id: 1, column_id: 8, value: 2, expected_version: 0 },
    ]),
  );
  await expect(page.getByText("All changes saved", { exact: true })).toBeVisible();
});

test("Grade 4 second-language grid shows only the three-level rubric", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  await mockGrid(page, fixture(4));
  await page.goto(`${teacherUrl}/classes/1/german?semester=1`);
  await expect(
    page.getByText("Grade 4 German and French use only the 1–2–3 scale.", { exact: true }),
  ).toBeVisible();
  const categories = page.getByRole("group", { name: "Assessment categories", exact: true });
  await expect(categories.getByRole("button", { name: /Exams|Homework/ })).toHaveCount(0);
  await expect(page.getByTestId("grade-grid-surface").getByRole("textbox")).toHaveCount(0);
  await expect(page.getByText("Needs support", { exact: false })).toBeVisible();
});

test("clearing a saved grade stays blank after save", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const grid = fixture();
  grid.rows[0].cells["1"] = { value: 60, version: 2 };
  let saved: SaveRequest | undefined;
  await mockGrid(page, grid, (body) => {
    saved = body;
  });
  await page.goto(`${teacherUrl}/classes/1/german?semester=1`);
  const cell = page.getByTestId("cell-1-1").getByRole("textbox");
  await cell.fill("");
  await page.getByTestId("save-grid").click();
  await expect(page.getByText("All changes saved", { exact: true })).toBeVisible();
  await expect(cell).toHaveValue("");
  expect(saved?.cells[0]).toEqual({
    student_id: 1,
    column_id: 1,
    value: null,
    expected_version: 2,
  });
});

for (const latest of ["85", "60", ""]) {
  test(`edits made during save survive (${latest || "cleared"})`, async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
    const grid = fixture();
    grid.rows[0].cells["1"] = { value: 60, version: 2 };
    const pending = Promise.withResolvers<void>();
    const requests: SaveRequest[] = [];
    await mockGrid(page, grid, async (body) => {
      requests.push(body);
      if (requests.length === 1) await pending.promise;
    });
    await page.goto(`${teacherUrl}/classes/1/german?semester=1`);
    const cell = page.getByTestId("cell-1-1").getByRole("textbox");
    await cell.fill("80");
    await page.getByTestId("save-grid").click();
    await expect.poll(() => requests.length).toBe(1);
    await cell.fill(latest);
    pending.resolve();
    await expect(page.getByTestId("save-grid")).toBeEnabled();
    await expect(cell).toHaveValue(latest);
    await page.getByTestId("save-grid").click();
    await expect(page.getByText("All changes saved", { exact: true })).toBeVisible();
    expect(requests[1]?.cells[0]).toEqual({
      student_id: 1,
      column_id: 1,
      value: latest === "" ? null : Number(latest),
      expected_version: 3,
    });
  });
}

test("partial saves retain unapplied drafts and leave the original snapshot intact", () => {
  const grid = fixture();
  grid.rows[0].cells["1"] = { value: 60, version: 2 };
  const applied: DirtyCell = { studentId: 1, columnId: 1, value: null, expectedVersion: 2 };
  const conflicted: DirtyCell = { studentId: 1, columnId: 2, value: 85, expectedVersion: 0 };
  const rejected: DirtyCell = { studentId: 1, columnId: 3, value: 95, expectedVersion: 0 };
  const draft = { "1:1": applied, "1:2": conflicted, "1:3": rejected };
  const submitted = {
    draft,
    cells: Object.values(draft).map((cell) => ({
      student_id: cell.studentId,
      column_id: cell.columnId,
      value: cell.value,
      expected_version: cell.expectedVersion,
    })),
  };
  const result = mergeSavedGrid(grid, draft, submitted, [
    { student_id: 1, column_id: 1, version: 3 },
  ]);
  expect(result.grid.rows[0].cells).toEqual({ "1": { value: null, version: 3 } });
  expect(result.dirty).toEqual({ "1:2": conflicted, "1:3": rejected });
  expect(grid.rows[0].cells["1"]).toEqual({ value: 60, version: 2 });
  expect(draft["1:1"]).toBe(applied);
});
