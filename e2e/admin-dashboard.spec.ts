import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import type {
  AdminActionPage,
  AuditPageOut,
  ClassOut,
  DashboardOut,
  JobOut,
  MeOut,
  MissingCell,
  StudentPage,
  UserOut,
  YearOut,
} from "../packages/api-client/src/index";
import { adminOrigin } from "./helpers/origins";

const en = JSON.parse(readFileSync("packages/i18n/src/locales/en.json", "utf8")) as {
  adminDashboard: {
    term: { openLifecycle: string };
    steps: {
      activateYear: { title: string };
      collectGrades: { title: string; withoutFields: string };
    };
    completion: { allComplete: string; details: string };
    missing: { tableLabel: string };
    problems: { unassignedRoles: string };
  };
  coordinator: { tableLabel: string };
  lifecycle: { activate: string };
  subjects: { german: string };
  audit: { actor: string; dateFrom: string; exportCsv: string; studentFilter: string };
  changes: { title: string; empty: string };
};

const admin: MeOut = {
  id: 1,
  full_name: "Synthetic Admin",
  email: "admin@example.test",
  is_admin: true,
  is_coordinator: false,
  assignments: [],
};

const completionRow = {
  class_id: 11,
  class_name: "5/A",
  grade_level: 5,
  subject: "english",
  roster_count: 2,
  active_columns: 2,
  expected_cells: 4,
  filled_cells: 3,
  missing_cells: 1,
  percent: 75,
};

const dashboard: DashboardOut = {
  term: {
    year_id: 7,
    year_label: "2030-2031",
    year_status: "active",
    semester_id: 70,
    semester_number: 1,
    semester_status: "open",
    semesters: [
      { id: 70, number: 1, status: "open" },
      { id: 71, number: 2, status: "locked" },
    ],
  },
  next_step: {
    code: "collect_grades",
    semester_number: 1,
    completion_percent: 75,
    missing_cells: 1,
    blockers: [],
  },
  overview: {
    year_label: "2030-2031",
    semester_id: 70,
    semester_number: 1,
    students: 2,
    classes: 1,
    active_teachers: 3,
    active_grants: 0,
    recent_saves: 4,
    missing_assignments: 1,
  },
  completion: {
    semester_id: 70,
    semester_number: 1,
    expected_cells: 4,
    filled_cells: 3,
    missing_cells: 1,
    percent: 75,
    complete_rows: 0,
    incomplete_rows: 1,
    rows: [
      completionRow,
      { ...completionRow, subject: "german", roster_count: 0, active_columns: 1 },
    ],
  },
  problems: {
    semester_id: 70,
    unassigned_roles: {
      count: 1,
      items: [{ class_id: 11, class_name: "5/A", grade_level: 5, role: "skills" }],
    },
    classes_without_fields: { count: 0, items: [] },
    teachers_without_report_name: { count: 0, items: [] },
    teachers_without_signature: { count: 0, items: [] },
    students_without_number: { count: 0, items: [] },
    students_without_language: { count: 0, items: [] },
  },
  readiness: [
    {
      kind: "english_middle",
      eligible_classes: 1,
      complete_classes: 0,
      students: 2,
      expected_cells: 4,
      filled_cells: 3,
      percent: 75,
    },
  ],
};

const missing: MissingCell[] = [
  {
    student_id: 21,
    school_number: 512,
    student_name: "Synthetic Pupil",
    column_id: 31,
    field_name: "Speaking",
    owner_role: "skills",
    teacher_id: null,
    teacher_name: null,
  },
];

const jobs: JobOut[] = [];
const teacher: UserOut = {
  id: 5,
  full_name: "Synthetic Teacher",
  email: "teacher@example.test",
  is_active: true,
  teaching_field: "english",
  teaching_stage: "middle",
};

/** Every request stays in this browser context; nothing touches a school database. */
async function mockApi(page: Page, exports: URL[] = []) {
  await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/api/me") return route.fulfill({ json: admin });
    if (path === "/api/dashboard") return route.fulfill({ json: dashboard });
    if (path === "/api/jobs") return route.fulfill({ json: jobs });
    if (path === "/api/admin/actions")
      return route.fulfill({ json: { items: [], next_cursor: null } satisfies AdminActionPage });
    if (path === "/api/coordinator/classes/11/missing") return route.fulfill({ json: missing });
    if (path === "/api/classes") return route.fulfill({ json: [] satisfies ClassOut[] });
    if (path === "/api/users") return route.fulfill({ json: [teacher] });
    if (path === "/api/audit")
      return route.fulfill({ json: { items: [], next_cursor: null } satisfies AuditPageOut });
    if (path === "/api/admin/students")
      return route.fulfill({ json: { items: [], next_cursor: null } satisfies StudentPage });
    if (path === "/api/audit/export.csv") {
      exports.push(url);
      return route.fulfill({ contentType: "text/csv", body: "id\n" });
    }
    return route.abort();
  });
}

for (const size of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test(`the dashboard shows the next step and drills into missing grades at ${size.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(size);
    await mockApi(page);
    await page.goto(`${adminOrigin}/admin/`);

    await expect(
      page.getByText(en.adminDashboard.steps.collectGrades.title.replace("{{number}}", "1"), {
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByText(en.adminDashboard.problems.unassignedRoles, { exact: true }),
    ).toBeVisible();
    // The page itself never scrolls sideways; wide tables scroll inside their card.
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    // Administrators see their recent changes with a way to the full list.
    const changes = page.getByTestId("recent-changes-card");
    await expect(changes.getByRole("heading", { name: en.changes.title })).toBeVisible();
    await expect(changes.getByText(en.changes.empty)).toBeVisible();

    await page.getByRole("button", { name: en.adminDashboard.completion.details }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("cell", { name: /Synthetic Pupil/ })).toBeVisible();
    await expect(dialog.getByText("Speaking")).toBeVisible();
  });
}

test("the old coordinator page opens the dashboard", async ({ page }) => {
  await mockApi(page);
  await page.goto(`${adminOrigin}/admin/coordinator`);
  await expect(page).toHaveURL(`${adminOrigin}/admin/`);
  const navigation = page.getByRole("navigation").first();
  await expect(navigation.getByRole("link", { name: "Students", exact: true })).toBeVisible();
  await expect(navigation.getByRole("link", { name: "Coordinator overview" })).toHaveCount(0);
});

test("the dashboard follows a lifecycle change made on another page", async ({ page }) => {
  await mockApi(page);
  let year: YearOut = {
    id: 7,
    label: "2030-2031",
    status: "setup",
    semesters: [
      { id: 70, number: 1, status: "locked" },
      { id: 71, number: 2, status: "locked" },
    ],
    missing_school_numbers: 0,
  };
  const inSetup: DashboardOut = {
    ...dashboard,
    term: { ...dashboard.term, year_status: "setup", semester_status: "locked" },
    next_step: {
      code: "activate_year",
      semester_number: null,
      completion_percent: null,
      missing_cells: null,
      blockers: [],
    },
    completion: null,
    readiness: [],
  };
  await page.route("**/api/dashboard", (route) =>
    route.fulfill({ json: year.status === "setup" ? inSetup : dashboard }),
  );
  await page.route("**/api/admin/years", (route) => route.fulfill({ json: [year] }));
  await page.route("**/api/admin/years/7/activate", (route) => {
    year = {
      ...year,
      status: "active",
      semesters: [{ ...year.semesters[0]!, status: "open" }, year.semesters[1]!],
    };
    return route.fulfill({ json: year });
  });

  await page.goto(`${adminOrigin}/admin/`);
  await expect(
    page.getByText(en.adminDashboard.steps.activateYear.title.replace("{{year}}", "2030-2031"), {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("link", { name: en.adminDashboard.term.openLifecycle }).click();
  await page.getByRole("button", { name: en.lifecycle.activate, exact: true }).click();
  await expect(page.getByTestId("lifecycle-year")).toHaveAttribute("data-year-status", "active");

  // Back within the query's 30-second freshness window: the next step must not still say
  // "activate" for a year that is already active.
  await page.goBack();
  await expect(
    page.getByText(en.adminDashboard.steps.collectGrades.title.replace("{{number}}", "1"), {
      exact: true,
    }),
  ).toBeVisible();
});

test("a grid with pupils but no fields is not reported as complete", async ({ page }) => {
  await mockApi(page);
  const complete = { ...completionRow, filled_cells: 4, missing_cells: 0, percent: 100 };
  const withoutFields = {
    ...completionRow,
    subject: "german",
    active_columns: 0,
    expected_cells: 0,
    filled_cells: 0,
    missing_cells: 0,
    percent: 100,
  };
  await page.route("**/api/dashboard", (route) =>
    route.fulfill({
      json: {
        ...dashboard,
        next_step: {
          code: "collect_grades",
          semester_number: 1,
          completion_percent: 100,
          missing_cells: 0,
          blockers: [{ code: "classes_without_fields", count: 1 }],
        },
        completion: {
          ...dashboard.completion!,
          filled_cells: 4,
          missing_cells: 0,
          percent: 100,
          complete_rows: 1,
          incomplete_rows: 1,
          rows: [complete, withoutFields],
        },
      } satisfies DashboardOut,
    }),
  );
  await page.goto(`${adminOrigin}/admin/`);

  await expect(
    page.getByText(en.adminDashboard.steps.collectGrades.withoutFields.replace("{{count}}", "1"), {
      exact: true,
    }),
  ).toBeVisible();
  // The default "incomplete" view keeps the field-less grid instead of an all-clear.
  const table = page.getByRole("table", { name: en.coordinator.tableLabel });
  await expect(table.getByRole("row").filter({ hasText: en.subjects.german })).toBeVisible();
  await expect(page.getByText(en.adminDashboard.completion.allComplete)).toHaveCount(0);
});

test("the audit CSV export carries the table's filters", async ({ page }) => {
  const exports: URL[] = [];
  await mockApi(page, exports);
  await page.goto(`${adminOrigin}/admin/audit`);
  await page
    .getByLabel(en.audit.actor, { exact: true })
    .selectOption({ label: "Synthetic Teacher" });
  await page.getByLabel(en.audit.dateFrom, { exact: true }).fill("2030-09-01");
  await page.getByRole("button", { name: en.audit.exportCsv }).click();
  await expect.poll(() => exports.length).toBe(1);
  expect(Object.fromEntries(exports[0]!.searchParams)).toEqual({
    actor_id: "5",
    date_from: "2030-09-01T00:00:00",
  });
});
