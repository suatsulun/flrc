import { mergeSavedGrid } from "../apps/teacher/src/grid/merge-saved-grid";
import type { DirtyCell } from "../apps/teacher/src/grid/dirty-store";
import { useDirtyStore } from "../apps/teacher/src/grid/dirty-store";
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
      .filter((c) => grade !== 4 || c.value_type !== "score"),
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
                subject: grid.meta.subject,
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

test("Grade 4 second-language grid shows ratings and teacher notes without numeric scores", async ({
  page,
}) => {
  await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  await mockGrid(page, fixture(4));
  await page.goto(`${teacherUrl}/classes/1/german?semester=1`);
  await expect(
    page.getByText(
      "Grade 4 German and French use 1–2–3 assessments and teacher comments, without numeric scores.",
      { exact: true },
    ),
  ).toBeVisible();
  const categories = page.getByRole("group", { name: "Assessment categories", exact: true });
  await expect(categories.getByRole("button", { name: /Exams|Homework/ })).toHaveCount(0);
  await expect(page.getByTestId("grade-grid-surface").getByRole("textbox")).toHaveCount(0);
  await expect(page.getByText("Needs improvement", { exact: false })).toBeVisible();
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

for (const width of [1536, 390]) {
  test(`notes filter isolates comments and bulk ratings cover hidden categories at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
    const grid = fixture();
    grid.rows[0].cells["1"] = { value: 82, version: 2 };
    grid.rows[0].cells["15"] = { value: "Keep this teacher note", version: 3 };
    const saves: SaveRequest[] = [];
    await mockGrid(page, grid, (body) => {
      saves.push(body);
    });
    await page.goto(`${teacherUrl}/classes/1/german?semester=1`);
    await page.getByRole("button", { name: "Teacher notes 1", exact: true }).click();
    if (width > 500) {
      await expect(page.getByTestId("assessment-heading")).toHaveText(["Teacher’s comments"]);
      await expect(page.getByTestId("grade-grid-surface").getByRole("textbox")).toHaveCount(0);
    } else {
      await expect(page.getByText(assessments[4][0], { exact: true })).toHaveCount(0);
    }
    await expect(page.getByText("Keep this teacher note", { exact: true })).toBeVisible();
    await page.getByTestId("bulk-ratings-student-1").click();
    await page.getByTestId("bulk-rating-3").click();
    expect(saves).toHaveLength(0);
    await expect(page.getByText("Keep this teacher note", { exact: true })).toBeVisible();
    await page.getByTestId("save-grid").click();
    await expect.poll(() => saves.length).toBe(1);
    expect(saves[0].cells).toEqual(
      grid.columns
        .filter((c) => c.value_type === "scale3")
        .map((c) => ({
          student_id: 1,
          column_id: c.id,
          value: 3,
          expected_version: 0,
        })),
    );
    await expect(page.getByTestId("save-grid")).toBeDisabled();
    await page.getByTestId("bulk-ratings-class").click();
    await page.getByTestId("bulk-rating-2").click();
    await page.getByTestId("save-grid").click();
    await expect.poll(() => saves.length).toBe(2);
    expect(saves[1].cells).toHaveLength(40);
    for (const cell of saves[1].cells) {
      expect(cell.value).toBe(2);
      expect(cell.expected_version).toBe(cell.student_id === 1 ? 1 : 0);
      expect(cell.column_id).toBeGreaterThanOrEqual(5);
      expect(cell.column_id).toBeLessThanOrEqual(14);
    }
    await expect(page.getByTestId("save-grid")).toBeDisabled();
    await page.getByRole("button", { name: "All assessments 15", exact: true }).click();
    if (width > 500)
      await expect(page.getByTestId("cell-1-1").getByRole("textbox")).toHaveValue("82");
    else
      await expect(
        page.getByRole("textbox", { name: `${names[0]} — Exam 1`, exact: true }),
      ).toHaveValue("82");
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  });
}

for (const subject of ["german", "french", "english"] as const) {
  for (const locked of [false, true]) {
    test(`${subject} ratings show their labels ${locked ? "when locked" : "when editable"}`, async ({
      page,
    }) => {
      await page.addInitScript(() => localStorage.setItem("i18nextLng", "tr"));
      const grid = fixture(4);
      grid.meta.subject = subject;
      grid.meta.semester_status = locked ? "locked" : "open";
      for (const row of grid.rows) {
        for (const column of grid.columns.filter((item) => item.value_type === "scale3"))
          row.cells[column.id] = { value: (column.id % 3) + 1, version: 1 };
      }
      await mockGrid(page, grid);
      await page.goto(`${teacherUrl}/classes/1/${subject}?semester=1`);
      const surface = page.getByTestId("grade-grid-surface");
      const cell = page.getByTestId("cell-1-5");
      await expect(cell).toContainText("Çok iyi");
      await expect(surface).toContainText("Geliştirilmeli");
      await expect(surface).toContainText("İyi");
      if (subject === "english") await expect(cell).toContainText("🙂");
      else await expect(surface).not.toContainText(/🙂|😐|🙁/);
      if (locked) {
        await expect(page.getByTestId("bulk-ratings-class")).toHaveCount(0);
        await expect(page.getByTestId("bulk-ratings-student-1")).toHaveCount(0);
        await expect(cell.getByRole("button")).toHaveCount(0);
      } else {
        await cell.getByRole("button").press("1");
        await expect(cell).toContainText("Geliştirilmeli");
      }
    });
  }
}

for (const value of [1, 2, 3] as const) {
  test(`bulk draft ${value} preserves versions, scores, notes, and unrelated pupils`, () => {
    const store = useDirtyStore;
    store.getState().clearAll();
    const grid = fixture();
    grid.rows[0].cells["5"] = { value: 2, version: 7 };
    grid.rows[0].cells["6"] = { value, version: 4 };
    const score = { studentId: 1, columnId: 1, value: 90, expectedVersion: 2 };
    const note = { studentId: 1, columnId: 15, value: "Unsaved note", expectedVersion: 3 };
    store.getState().setCell(score);
    store.getState().setCell(note);
    store.getState().setCell({ studentId: 1, columnId: 5, value: 1, expectedVersion: 6 });
    store.getState().setCell({ studentId: 2, columnId: 5, value: 2, expectedVersion: 9 });
    store.getState().setRatings(grid, value, 1);
    const draft = store.getState().cells;
    expect(draft["1:1"]).toBe(score);
    expect(draft["1:15"]).toBe(note);
    expect(draft["1:6"]).toBeUndefined();
    expect(draft["2:5"]).toEqual({ studentId: 2, columnId: 5, value: 2, expectedVersion: 9 });
    if (value === 2) expect(draft["1:5"]).toBeUndefined();
    else expect(draft["1:5"]?.expectedVersion).toBe(6);
    expect(draft["1:14"]).toEqual({ studentId: 1, columnId: 14, value, expectedVersion: 0 });
    const snapshot = store.getState().cells;
    grid.meta.semester_status = "locked";
    store.getState().setRatings(grid, 3);
    expect(store.getState().cells).toBe(snapshot);
    expect(grid.rows[0].cells["5"]).toEqual({ value: 2, version: 7 });
    store.getState().clearAll();
  });
}

for (const latest of [1, 2] as const) {
  test(`bulk choice ${latest} during a save remains unsaved with the new versions`, async ({
    page,
  }) => {
    await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
    const grid = fixture();
    grid.rows[0].cells["5"] = { value: 1, version: 1 };
    const pending = Promise.withResolvers<void>();
    const saves: SaveRequest[] = [];
    await mockGrid(page, grid, async (body) => {
      saves.push(body);
      if (saves.length === 1) await pending.promise;
    });
    await page.goto(`${teacherUrl}/classes/1/german?semester=1`);
    await page.getByTestId("bulk-ratings-student-1").click();
    await page.getByTestId("bulk-rating-3").click();
    await page.getByTestId("save-grid").click();
    await expect.poll(() => saves.length).toBe(1);
    await page.getByTestId("bulk-ratings-class").click();
    await page.getByTestId(`bulk-rating-${latest}`).click();
    pending.resolve();
    await expect(page.getByTestId("save-grid")).toBeEnabled();
    await page.getByTestId("save-grid").click();
    await expect.poll(() => saves.length).toBe(2);
    expect(saves[1].cells).toHaveLength(40);
    expect(saves[1].cells.every((cell) => cell.value === latest)).toBe(true);
    expect(
      saves[1].cells.find((cell) => cell.student_id === 1 && cell.column_id === 5)
        ?.expected_version,
    ).toBe(2);
    await expect(page.getByTestId("save-grid")).toBeDisabled();
  });
}

for (const subject of ["english", "german", "french"] as const) {
  for (const width of [1366, 390]) {
    test(`grade 4 ${subject} has a final notes category and saves comments at ${width}px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
      const grid = fixture(4);
      grid.meta.subject = subject;
      let saved: SaveRequest | undefined;
      await mockGrid(page, grid, (body) => {
        saved = body;
      });
      await page.goto(`${teacherUrl}/classes/1/${subject}?semester=1`);
      const categories = page.getByRole("group", { name: "Assessment categories", exact: true });
      await expect(categories.getByRole("button").last()).toHaveText("Teacher notes1");
      await categories.getByRole("button").last().click();
      await expect(page.getByText(assessments[4][0], { exact: true })).toHaveCount(0);
      await page
        .getByRole("button", { name: `${names[0]} — Teacher’s comments`, exact: true })
        .click();
      await page.getByRole("dialog").getByRole("textbox").fill("Synthetic teacher feedback");
      await page.getByRole("button", { name: "Done", exact: true }).click();
      await page.getByTestId("save-grid").click();
      await expect
        .poll(() => saved?.cells)
        .toEqual([
          {
            student_id: 1,
            column_id: 15,
            value: "Synthetic teacher feedback",
            expected_version: 0,
          },
        ]);
      await expect(page.getByText("All changes saved", { exact: true })).toBeVisible();
    });
  }
}

for (const width of [1366, 390]) {
  test(`unconfigured notes remain discoverable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
    const grid = fixture(4);
    grid.columns = grid.columns.filter((column) => column.value_type !== "text");
    await mockGrid(page, grid);
    await page.goto(`${teacherUrl}/classes/1/german?semester=1`);
    await page.getByRole("button", { name: "Teacher notes 0", exact: true }).click();
    await expect(
      page.getByText(
        "No teacher notes field is configured for this subject. An administrator can add a text field under Columns.",
        { exact: true },
      ),
    ).toBeVisible();
  });
}

const englishDefaults = JSON.parse(
  execFileSync("apps/backend/.venv/bin/python", [
    "-c",
    "import json; from flrc.cli import ENGLISH_58, REPORT_LABELS; print(json.dumps([dict(labels=REPORT_LABELS[k], owner_role=r, value_type=v) for k,r,v,_ in ENGLISH_58]))",
  ]).toString(),
) as Array<{ labels: Record<string, string>; owner_role: string; value_type: string }>;

for (const locale of ["tr", "en", "de", "fr"]) {
  test(`middle English uses all 11 score columns with slanted headers in ${locale}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.addInitScript((lng) => {
      localStorage.setItem("i18nextLng", lng);
      localStorage.setItem("flrc-theme", "light");
    }, locale);
    const grid = fixture(5);
    grid.meta.subject = "english";
    grid.columns = englishDefaults.map((column, i) => ({
      id: i + 1,
      label: column.labels[locale],
      group: null,
      value_type: column.value_type,
      owner_role: column.owner_role,
      owner_name: "Synthetic Teacher",
      owned_by_you: column.owner_role === "main",
      position: i + 1,
    }));
    let saved: SaveRequest | undefined;
    await mockGrid(page, grid, (body) => {
      saved = body;
    });
    await page.goto(`${teacherUrl}/classes/1/english?semester=1`);
    const surface = page.getByTestId("grade-grid-surface");
    await expect(surface).toHaveAttribute("data-layout", "english-overview");
    await expect(page.getByTestId("assessment-heading")).toHaveCount(12);
    await expect(surface.getByRole("textbox")).toHaveCount(44);
    await page.evaluate(() => document.fonts.ready);
    const bounds = await surface.evaluate((element) => {
      const headers = element.querySelector("thead")!.getBoundingClientRect();
      return {
        pageOverflow: document.documentElement.scrollWidth > window.innerWidth,
        labelsFit: [...element.querySelectorAll(".english-slanted-label")].every((label) => {
          const rect = label.getBoundingClientRect();
          return (
            rect.top >= headers.top - 1 &&
            rect.bottom <= headers.bottom &&
            rect.right <= headers.right
          );
        }),
        inputWidths: [...element.querySelectorAll("input")].map(
          (input) => input.getBoundingClientRect().width,
        ),
      };
    });
    expect(bounds.pageOverflow).toBe(false);
    expect(bounds.labelsFit).toBe(true);
    expect(Math.min(...bounds.inputWidths)).toBeGreaterThanOrEqual(56);
    const first = page.getByTestId("cell-1-1").getByRole("textbox");
    await first.fill("82");
    await first.press("ArrowRight");
    await expect(page.getByTestId("cell-1-2").getByRole("textbox")).toBeFocused();
    const last = page.getByTestId("cell-1-11").getByRole("textbox");
    await last.focus();
    await last.press("ArrowRight");
    await expect(page.getByTestId("cell-1-12").getByRole("button")).toBeFocused();
    await page.getByTestId("save-grid").click();
    await expect
      .poll(() => saved?.cells)
      .toEqual([{ student_id: 1, column_id: 1, value: 82, expected_version: 0 }]);
    await page.screenshot({ path: testInfo.outputPath("english-45-degrees.png"), fullPage: true });
    await page.setViewportSize({ width: 1280, height: 900 });
    await expect(surface).toHaveAttribute("data-layout", "english-overview");
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await page.setViewportSize({ width: 768, height: 900 });
    await expect(surface).toHaveAttribute("data-layout", "paged");
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  });
}
