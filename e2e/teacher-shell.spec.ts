import { expect, test, type Page } from "@playwright/test";
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

const emptyScope: PreviewScopeOut = {
  year_id: 1,
  year_label: "Synthetic year",
  semester_id: 1,
  semester_number: 1,
  semesters: [{ id: 1, number: 1, status: "open" }],
  classes: [],
};

async function mockApi(page: Page, role: Role, catalog: ClassCatalogOut[]) {
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
    if (sheetClass) return route.fulfill({ json: sheet(sheetClass) });
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
