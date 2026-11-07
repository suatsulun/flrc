import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import type {
  AdminClassOut,
  ArchiveClassOut,
  ArchiveGridOut,
  ArchiveYearOut,
  HistoryCell,
  MeOut,
  StudentHistoryOut,
  StudentPage,
  YearOut,
} from "../packages/api-client/src/index";
import { adminOrigin } from "./helpers/origins";

const en = JSON.parse(readFileSync("packages/i18n/src/locales/en.json", "utf8")) as {
  classWorkspace: { year: string; semester: string };
  students: Record<string, string>;
  studentSearch: Record<string, string>;
};

const admin: MeOut = {
  id: 1,
  full_name: "Synthetic Admin",
  email: "admin@example.test",
  is_admin: true,
  is_coordinator: false,
  assignments: [],
};

const score = (column_id: number, label: string, value: number | string): HistoryCell => ({
  column_id,
  label,
  subject: "english",
  value_type: typeof value === "number" ? "score" : "text",
  value,
});

// Oldest first, as the API returns them. The newest year has no grades yet, so the page
// opens on 2029-2030, whose latest graded semester is the first.
const history: StudentHistoryOut = {
  student_id: 21,
  school_number: 512,
  full_name: "Synthetic Pupil",
  years: [
    {
      year_id: 3,
      label: "2028-2029",
      year_status: "archived",
      school_number: 301,
      class_name: "3/B",
      language: null,
      semesters: [
        { number: 1, status: "locked", cells: [score(31, "Reading", 88)] },
        {
          number: 2,
          status: "locked",
          cells: [score(32, "Reading", 92), score(33, "Comment", "Synthetic steady progress")],
        },
      ],
    },
    {
      year_id: 4,
      label: "2029-2030",
      year_status: "archived",
      school_number: 401,
      class_name: "4/B",
      language: "german",
      semesters: [
        { number: 1, status: "locked", cells: [score(41, "Speaking", 75)] },
        { number: 2, status: "locked", cells: [] },
      ],
    },
    {
      year_id: 5,
      label: "2030-2031",
      year_status: "active",
      school_number: 512,
      class_name: "5/B",
      language: "german",
      semesters: [
        { number: 1, status: "locked", cells: [] },
        { number: 2, status: "open", cells: [] },
      ],
    },
  ],
};

const year: YearOut = {
  id: 5,
  label: "2030-2031",
  status: "active",
  semesters: [
    { id: 50, number: 1, status: "locked" },
    { id: 51, number: 2, status: "open" },
  ],
  missing_school_numbers: 0,
};

const schoolClass: AdminClassOut = {
  id: 55,
  year_id: 5,
  grade_level: 5,
  section: "B",
  name: "5/B",
  student_count: 1,
};

const students: StudentPage = {
  items: [
    {
      id: 21,
      school_number: 512,
      full_name: "Synthetic Pupil With A Rather Long Family Name",
      year_id: 5,
      class_id: 55,
    },
  ],
  next_cursor: null,
};

const archiveYear: ArchiveYearOut = { id: 3, label: "2028-2029", status: "archived" };
const archiveClass: ArchiveClassOut = { id: 33, name: "3/B", grade_level: 3 };
const archiveComment = "Synthetic pupil took part keenly all term.";
const archiveGrid: ArchiveGridOut = {
  class_name: "3/B",
  semester: 1,
  subject: "english",
  columns: [
    { id: 1, label: "Participates in classroom activities", value_type: "scale3" },
    { id: 2, label: "Follows classroom rules and routines", value_type: "scale3" },
    { id: 3, label: "Reading", value_type: "score" },
    { id: 4, label: "Speaking", value_type: "score" },
    { id: 5, label: "Teacher’s comments", value_type: "text" },
  ],
  rows: [1, 2, 3].map((n) => ({
    student_id: 30 + n,
    school_number: 3000 + n,
    full_name: `Synthetic Archived Pupil With A Long Name ${n}`,
    cells: { "1": 1, "2": 3, "3": 80 + n, "4": null, "5": archiveComment },
  })),
};

/** Every request stays in this browser context; nothing touches a school database. */
async function mockApi(page: Page) {
  await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/me") return route.fulfill({ json: admin });
    if (path === "/api/archive/students/21/history") return route.fulfill({ json: history });
    if (path === "/api/admin/years") return route.fulfill({ json: [year] });
    if (path === "/api/admin/years/5/classes") return route.fulfill({ json: [schoolClass] });
    if (path === "/api/admin/students") return route.fulfill({ json: students });
    if (path === "/api/archive/years") return route.fulfill({ json: [archiveYear] });
    if (path === "/api/archive/years/3/classes") return route.fulfill({ json: [archiveClass] });
    if (path === "/api/archive/classes/33/grid") return route.fulfill({ json: archiveGrid });
    return route.abort();
  });
}

const noSidewaysScroll = (page: Page) =>
  page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  );

for (const size of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test(`the history shows one chosen year and semester at ${size.width}px`, async ({ page }) => {
    await page.setViewportSize(size);
    await mockApi(page);
    await page.goto(`${adminOrigin}/admin/students/21/history`);

    const yearSelect = page.getByLabel(en.classWorkspace.year, { exact: true });
    const semesters = page.getByRole("radiogroup", { name: en.classWorkspace.semester });
    const table = page.getByRole("table");
    const enrolment = (className: string, number: number) =>
      page.getByRole("heading", { name: `${className} · ${en.students.schoolNumber} ${number}` });

    // Default: the most recent year with grades, on its latest graded semester.
    await expect(yearSelect).toHaveValue("4");
    await expect(enrolment("4/B", 401)).toBeVisible();
    await expect(table.getByText("Speaking", { exact: true })).toBeVisible();
    await expect(page.getByText("Reading", { exact: true })).toHaveCount(0);
    expect(await noSidewaysScroll(page)).toBe(true);

    await semesters.getByRole("radio", { name: "S2" }).click();
    await expect(page).toHaveURL(/semester=2/);
    await expect(page.getByText(en.students.historyEmptyClosed, { exact: true })).toBeVisible();
    await expect(page.getByText("Speaking", { exact: true })).toHaveCount(0);

    // A new year opens on its own default semester.
    await yearSelect.selectOption("3");
    await expect(page).toHaveURL(/year=3/);
    await expect(page).not.toHaveURL(/semester=/);
    await expect(enrolment("3/B", 301)).toBeVisible();
    await expect(table.getByText("Reading", { exact: true })).toBeVisible();
    await expect(table.getByText("Synthetic steady progress", { exact: true })).toBeVisible();
    await expect(table.getByText("92", { exact: true })).toBeVisible();

    await yearSelect.selectOption("5");
    await expect(enrolment("5/B", 512)).toBeVisible();
    await expect(page.getByText(en.students.historyEmptyOpen, { exact: true })).toBeVisible();
    expect(await noSidewaysScroll(page)).toBe(true);

    // The URL alone restores the choice.
    await page.goto(`${adminOrigin}/admin/students/21/history?year=3&semester=1`);
    await expect(yearSelect).toHaveValue("3");
    await expect(table.getByText("88", { exact: true })).toBeVisible();
    await expect(page.getByText("92", { exact: true })).toHaveCount(0);
  });
}

test("student search results fit a phone and open the history", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto(`${adminOrigin}/admin/students`);

  const results = page.getByLabel(en.studentSearch.tableLabel, { exact: true });
  await expect(results.getByRole("row", { name: /Synthetic Pupil/ })).toContainText("5/B");
  expect(await noSidewaysScroll(page)).toBe(true);
  expect(await results.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(
    true,
  );

  await results.getByRole("link", { name: en.students.history, exact: true }).click();
  await expect(page).toHaveURL(/\/students\/21\/history/);
  await expect(page.getByRole("heading", { name: "Synthetic Pupil", exact: true })).toBeVisible();
});

test("the archive reads as a card per student on a phone and pins the name in the table", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto(`${adminOrigin}/admin/archive`);

  // The four pickers share two rows, each a full touch target.
  const pickers = [
    page.getByLabel("Academic year", { exact: true }),
    page.getByLabel("Classes", { exact: true }),
    page.getByLabel("Semester 1", { exact: true }),
    page.getByLabel("Subject", { exact: true }),
  ];
  const boxes = await Promise.all(pickers.map(async (picker) => (await picker.boundingBox())!));
  for (const box of boxes) expect(box.height).toBeGreaterThanOrEqual(40);
  expect(boxes[0].y).toBe(boxes[1].y);
  expect(boxes[2].y).toBe(boxes[3].y);
  expect(boxes[2].y).toBeGreaterThan(boxes[0].y);

  // Cards by default, with every archived column and value.
  const viewSwitch = page.getByRole("radiogroup", { name: "View", exact: true });
  await expect(viewSwitch.getByRole("radio", { name: "Cards", exact: true })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  const cards = page.getByTestId("student-grade-card");
  await expect(cards).toHaveCount(3);
  const first = cards.first();
  await expect(first).toContainText("Synthetic Archived Pupil With A Long Name 1");
  await expect(first).toContainText("3001");
  for (const column of archiveGrid.columns) {
    await expect(first.getByText(column.label, { exact: true })).toBeVisible();
  }
  await expect(first.getByText("81", { exact: true })).toBeVisible();
  await expect(first.getByText(archiveComment, { exact: true })).toBeVisible();
  expect(await noSidewaysScroll(page)).toBe(true);

  // The table pins the student column at 10rem while the grades scroll.
  const tableRadio = viewSwitch.getByRole("radio", { name: "Table", exact: true });
  await tableRadio.click();
  await expect(tableRadio).toHaveAttribute("aria-checked", "true");
  await expect(cards).toHaveCount(0);
  const table = page.getByLabel("Archived grade table", { exact: true });
  const nameHeader = table.getByRole("columnheader", { name: "Full name", exact: true });
  expect(Math.round((await nameHeader.boundingBox())!.width)).toBe(160);
  const nameCell = table.getByRole("cell", { name: /Name 1$/ });
  const before = (await nameCell.boundingBox())!.x;
  await table.evaluate((element) => element.scrollBy({ left: 300 }));
  expect(await table.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  expect((await nameCell.boundingBox())!.x).toBeCloseTo(before, 0);
  expect(await noSidewaysScroll(page)).toBe(true);

  // Wider screens keep the table and hide the switch.
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(viewSwitch).toBeHidden();
  await expect(table.getByRole("columnheader", { name: "Full name", exact: true })).toBeVisible();
});
