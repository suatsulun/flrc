import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import type {
  AdminClassOut,
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
  loading: string;
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

test("a new student search shows skeleton rows, not the previous results", async ({ page }) => {
  await mockApi(page);
  const searched = Promise.withResolvers<void>();
  // Registered after mockApi, so it answers the search first; the unfiltered list falls back.
  await page.route(
    (url) => url.pathname === "/api/admin/students",
    async (route) => {
      if (!new URL(route.request().url()).searchParams.get("q")) return route.fallback();
      await searched.promise;
      return route.fulfill({
        json: {
          items: [
            {
              id: 22,
              school_number: 513,
              full_name: "Synthetic Searched Pupil",
              year_id: 5,
              class_id: 55,
            },
          ],
          next_cursor: null,
        } satisfies StudentPage,
      });
    },
  );
  await page.goto(`${adminOrigin}/admin/students`);

  const results = page.getByLabel(en.studentSearch.tableLabel, { exact: true });
  const placeholders = results.locator("tbody tr[aria-hidden]");
  const loading = page.getByRole("status").filter({ hasText: en.loading });
  await expect(results.getByRole("row", { name: /Synthetic Pupil With/ })).toBeVisible();

  const search = page.getByLabel(en.studentSearch.searchLabel, { exact: true });
  await search.fill("Searched");
  // While the search runs, the previous results are gone and skeleton rows stand in; the
  // search box keeps focus, and one polite status says it is loading.
  await expect(placeholders).toHaveCount(8);
  await expect(results.getByText(/Synthetic Pupil With/)).toHaveCount(0);
  await expect(search).toBeFocused();
  await expect(loading).toHaveCount(1);

  searched.resolve();
  await expect(results.getByRole("row", { name: /Synthetic Searched Pupil/ })).toBeVisible();
  await expect(placeholders).toHaveCount(0);
  await expect(loading).toHaveCount(0);
});
