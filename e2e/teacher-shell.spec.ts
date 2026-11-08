import { expect, test, type Locator, type Page } from "@playwright/test";
import type {
  ClassCatalogOut,
  ClassSheetOut,
  MeOut,
  PreviewScopeOut,
  YearOut,
} from "../packages/api-client/src/index";
import { teacherOrigin } from "./helpers/origins";

type Role = "admin" | "coordinator" | "teacher";

function me(role: Role): MeOut {
  return {
    id: 1,
    full_name: "Synthetic User",
    email: "user@example.test",
    is_admin: role === "admin",
    is_coordinator: role === "coordinator",
    assignments: [],
  };
}

function englishClass(id: number, grade: number, section: string, roles: string[] = []) {
  return {
    id,
    name: `${grade}/${section}`,
    grade_level: grade,
    section,
    subjects: [
      {
        subject: "english",
        student_count: 0,
        column_count: 1,
        owner_roles: ["main"],
        my_roles: roles,
        can_write: roles.length > 0,
      },
    ],
    assigned_roles: roles,
  } satisfies ClassCatalogOut;
}

function sheet(schoolClass: ClassCatalogOut): ClassSheetOut {
  return {
    class_id: schoolClass.id,
    class_name: schoolClass.name,
    grade_level: schoolClass.grade_level,
    year_id: 1,
    year_label: "Synthetic year",
    semester_id: 1,
    semester_number: 1,
    teachers: [],
    columns: [],
    students: [],
  };
}

/** A class sheet with grouped, 1-2-3 and long-labelled columns, wide enough to scroll on a phone. */
function filledSheet(schoolClass: ClassCatalogOut): ClassSheetOut {
  return {
    ...sheet(schoolClass),
    teachers: ["Synthetic Teacher"],
    columns: [
      { id: 1, label: "Progress Exam 1", group: "Reading", value_type: "score" },
      { id: 2, label: "Progress Exam 2", group: "Reading", value_type: "score" },
      { id: 3, label: "Reader 1", group: "Reading", value_type: "score" },
      {
        id: 4,
        label: "Participates in classroom activities",
        group: null,
        value_type: "scale3",
      },
      { id: 5, label: "Speaking", group: null, value_type: "score" },
      { id: 6, label: "Writing", group: null, value_type: "score" },
    ],
    students: [1, 2, 3].map((n) => ({
      student_id: 100 + n,
      school_number: 500 + n,
      full_name: `Synthetic Student ${n}`,
      values: [70 + n, 80 + n, null, 3, 60 + n, 90],
    })),
  };
}

const emptyScope: PreviewScopeOut = {
  year_id: 1,
  year_label: "Synthetic year",
  semester_id: 1,
  semester_number: 1,
  semesters: [{ id: 1, number: 1, status: "open" }],
  classes: [],
};

async function mockApi(
  page: Page,
  role: Role,
  catalog: ClassCatalogOut[],
  sheetOf: (schoolClass: ClassCatalogOut) => ClassSheetOut = sheet,
) {
  await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/me") return route.fulfill({ json: me(role) });
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
    if (path === "/api/class-catalog") return route.fulfill({ json: catalog });
    if (path === "/api/reports/preview/scope") return route.fulfill({ json: emptyScope });
    const sheetClass = catalog.find((item) => path === `/api/classes/${item.id}/sheet`);
    if (sheetClass) return route.fulfill({ json: sheetOf(sheetClass) });
    return route.fulfill({ json: [] });
  });
}

for (const role of ["admin", "coordinator", "teacher"] as const) {
  test(`${role}: the panel switch and the report section`, async ({ page }) => {
    const canOpenAdmin = role !== "teacher";
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, role, []);
    await page.goto(`${teacherOrigin}/`);

    // The way to the admin panel sits in the top bar, right after the language switch.
    const banner = page.getByRole("banner");
    await expect(banner.getByRole("radiogroup", { name: "Language" })).toBeVisible();
    const adminLink = page.getByRole("link", { name: "Admin panel", exact: true });
    if (canOpenAdmin) {
      await expect(banner.getByRole("link", { name: "Admin panel", exact: true })).toBeVisible();
      await expect(adminLink).toHaveCount(1);
    } else {
      await expect(adminLink).toHaveCount(0);
    }

    // Everyone gets both report entries, whatever they teach.
    const sidebar = page.getByRole("navigation", { name: "Main navigation" });
    await expect(sidebar.getByRole("link", { name: "Class report", exact: true })).toBeVisible();
    await expect(
      sidebar.getByRole("link", { name: "Report card preview", exact: true }),
    ).toBeVisible();

    // On a phone the switch moves into the menu.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("button", { name: "Menu", exact: true }).click();
    const drawer = page.locator("#app-shell-drawer");
    await expect(drawer.getByRole("link", { name: "Class report", exact: true })).toBeVisible();
    if (canOpenAdmin) {
      await expect(drawer.getByRole("link", { name: "Admin panel", exact: true })).toBeVisible();
    } else {
      await expect(drawer.getByRole("link", { name: "Admin panel", exact: true })).toHaveCount(0);
    }
  });
}

test("class report opens the user's own middle-school English class, else the first", async ({
  page,
}) => {
  const first = englishClass(11, 5, "A");
  const own = englishClass(12, 6, "B", ["main"]);
  const primary = englishClass(13, 3, "C", ["main"]);

  await mockApi(page, "teacher", [primary, first, own]);
  await page.goto(`${teacherOrigin}/class-report`);
  await expect(page).toHaveURL(new RegExp(`/class-report/${own.id}`));
  await expect(page.getByRole("heading", { level: 1 })).toContainText("6/B");

  await page.unrouteAll();
  await mockApi(page, "teacher", [primary, first, englishClass(12, 6, "B")]);
  await page.goto(`${teacherOrigin}/class-report`);
  await expect(page).toHaveURL(new RegExp(`/class-report/${first.id}`));
  await expect(page.getByRole("heading", { level: 1 })).toContainText("5/A");
});

test("class report and card preview explain when there is nothing to show", async ({ page }) => {
  await mockApi(page, "teacher", [englishClass(13, 3, "C", ["main"])]);
  await page.goto(`${teacherOrigin}/class-report`);
  await expect(page.getByText("No class reports to show", { exact: true })).toBeVisible();

  await page.getByRole("radio", { name: "Report card preview", exact: true }).click();
  await expect(page).toHaveURL(/\/card-preview/);
  await expect(page.getByText("No report cards to preview", { exact: true })).toBeVisible();
  await expect(page.getByText(/You have no class assignment in this school year/)).toBeVisible();
  // The mode switch leads back to the class report from here too.
  await expect(page.getByRole("radio", { name: "Class report", exact: true })).toBeVisible();
});

test("class report reads as a card per student on a phone and pins number and name in the table", async ({
  page,
}) => {
  const schoolClass = englishClass(11, 5, "A", ["main"]);
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page, "teacher", [schoolClass], filledSheet);
  await page.goto(`${teacherOrigin}/class-report/${schoolClass.id}`);
  const noSidewaysScroll = () => page.evaluate(() => document.documentElement.scrollWidth <= 390);

  // Phones open on cards: every student with every column, nothing scrolling sideways.
  const viewSwitch = page.getByRole("radiogroup", { name: "View", exact: true });
  const cardsRadio = viewSwitch.getByRole("radio", { name: "Cards", exact: true });
  const tableRadio = viewSwitch.getByRole("radio", { name: "Table", exact: true });
  await expect(cardsRadio).toHaveAttribute("aria-checked", "true");
  const cards = page.getByTestId("student-grade-card");
  await expect(cards).toHaveCount(3);
  const first = cards.first();
  for (const label of [
    "Progress Exam 1",
    "Progress Exam 2",
    "Reader 1",
    "Participates in classroom activities",
    "Speaking",
    "Writing",
  ]) {
    await expect(first.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(first).toContainText("Synthetic Student 1");
  await expect(first).toContainText("71");
  await expect(page.getByText("Very good")).toBeVisible();
  expect(await noSidewaysScroll()).toBe(true);
  for (const target of [
    cardsRadio,
    tableRadio,
    page.getByRole("button", { name: "5/A", exact: true }),
    page.getByRole("button", { name: "Print", exact: true }),
    page.getByRole("button", { name: "Download PDF", exact: true }),
  ]) {
    const box = await target.boundingBox();
    expect(box!.height).toBeGreaterThanOrEqual(40);
  }

  // The student being discussed stays marked; the arrow keys walk the class.
  // Every card has a drop shadow; the mark is the inset edge plus the active-row background.
  const mark = (card: Locator) =>
    card.evaluate((element) => {
      const style = getComputedStyle(element);
      return { background: style.backgroundColor, edge: style.boxShadow.includes("inset") };
    });
  const unmarked = await mark(cards.nth(1));
  await first.click();
  await expect(first).toBeFocused();
  const marked = await mark(first);
  expect(marked.edge).toBe(true);
  expect(unmarked.edge).toBe(false);
  expect(marked.background).not.toBe(unmarked.background);
  await page.keyboard.press("ArrowDown");
  await expect(cards.nth(1)).toBeFocused();
  expect(await mark(cards.nth(1))).toEqual(marked);
  expect(await mark(first)).toEqual(unmarked);
  await page.keyboard.press("ArrowUp");
  await expect(first).toBeFocused();

  // The table is one tap away and stays chosen; number and name stay put while grades scroll.
  await tableRadio.click();
  await expect(tableRadio).toHaveAttribute("aria-checked", "true");
  expect(await page.evaluate(() => localStorage.getItem("flrc-grade-phone-view"))).toBe("table");
  await expect(cards).toHaveCount(0);
  await page.reload();
  await expect(tableRadio).toHaveAttribute("aria-checked", "true");
  const table = page.locator("table.class-sheet");
  const numberHeader = table.getByRole("columnheader", { name: "No.", exact: true });
  const nameHeader = table.getByRole("columnheader", { name: "Student", exact: true });
  expect(Math.round((await numberHeader.boundingBox())!.width)).toBe(48);
  expect(Math.round((await nameHeader.boundingBox())!.width)).toBe(136);
  const row = table.getByRole("row", { name: "Synthetic Student 1", exact: true });
  const nameCell = row.getByRole("cell", { name: "Synthetic Student 1", exact: true });
  const before = (await nameCell.boundingBox())!.x;
  const surface = table.locator("xpath=..");
  await surface.evaluate((element) => element.scrollBy({ left: 200 }));
  expect(await surface.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  expect((await nameCell.boundingBox())!.x).toBeCloseTo(before, 0);
  expect(await noSidewaysScroll()).toBe(true);
  await row.click();
  await expect(row).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(table.getByRole("row", { name: "Synthetic Student 2", exact: true })).toBeFocused();

  // Wider screens always get the table at its full widths, without the switch.
  await cardsRadio.click();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(viewSwitch).toBeHidden();
  await expect(cards).toHaveCount(0);
  expect(Math.round((await numberHeader.boundingBox())!.width)).toBe(64);
  expect(Math.round((await nameHeader.boundingBox())!.width)).toBe(240);
});

test("a view chosen in another tab applies when the class report opens again", async ({ page }) => {
  const schoolClass = englishClass(11, 5, "A", ["main"]);
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page, "teacher", [schoolClass], filledSheet);
  await page.goto(`${teacherOrigin}/class-report/${schoolClass.id}`);
  const viewSwitch = page.getByRole("radiogroup", { name: "View", exact: true });
  await expect(viewSwitch.getByRole("radio", { name: "Cards", exact: true })).toHaveAttribute(
    "aria-checked",
    "true",
  );

  // Leave the class report without reloading, so nothing on this page listens for the change.
  await page.getByRole("radio", { name: "Report card preview", exact: true }).click();
  await expect(page).toHaveURL(/\/card-preview/);

  const other = await page.context().newPage();
  await other.setViewportSize({ width: 390, height: 844 });
  await mockApi(other, "teacher", [schoolClass], filledSheet);
  await other.goto(`${teacherOrigin}/class-report/${schoolClass.id}`);
  await other
    .getByRole("radiogroup", { name: "View", exact: true })
    .getByRole("radio", { name: "Table", exact: true })
    .click();
  await other.close();

  await page.getByRole("radio", { name: "Class report", exact: true }).click();
  await expect(viewSwitch.getByRole("radio", { name: "Table", exact: true })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  await expect(page.getByTestId("student-grade-card")).toHaveCount(0);
});
