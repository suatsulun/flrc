import { expect, test, type Page } from "@playwright/test";
import type {
  ClassCatalogOut,
  ClassSheetOut,
  MeOut,
  YearOut,
} from "../packages/api-client/src/index";
import { teacherOrigin } from "./helpers/origins";

const schoolClass: ClassCatalogOut = {
  id: 11,
  name: "5/A",
  grade_level: 5,
  section: "A",
  subjects: [
    {
      subject: "english",
      student_count: 1,
      column_count: 1,
      owner_roles: ["main"],
      my_roles: ["main"],
      can_write: true,
    },
  ],
  assigned_roles: ["main"],
};

const teacher: MeOut = {
  id: 1,
  full_name: "Synthetic Teacher",
  email: "teacher@example.test",
  is_admin: false,
  is_coordinator: false,
  assignments: [],
};

const year: YearOut = {
  id: 1,
  label: "Synthetic year",
  status: "active",
  missing_school_numbers: 0,
  semesters: [
    { id: 1, number: 1, status: "locked" },
    { id: 2, number: 2, status: "open" },
  ],
};

function sheet(semester: number): ClassSheetOut {
  return {
    class_id: schoolClass.id,
    class_name: schoolClass.name,
    grade_level: schoolClass.grade_level,
    year_id: year.id,
    year_label: year.label,
    semester_id: semester,
    semester_number: semester,
    teachers: ["Synthetic Teacher"],
    columns: [{ id: 1, label: "Exam", group: null, value_type: "score" }],
    students: [
      { student_id: 101, school_number: 501, full_name: "Synthetic Student", values: [80] },
    ],
  };
}

/**
 * The teacher API with a class sheet PDF and the second semester's sheet that answer only when
 * the test releases them; the second semester's sheet then fails.
 */
async function mockApi(page: Page, pdfHold: Promise<void>, secondSheetHold: Promise<void>) {
  const pdfRequests: string[] = [];
  await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/me") return route.fulfill({ json: teacher });
    if (url.pathname === "/api/academic-years") return route.fulfill({ json: [year] });
    if (url.pathname === "/api/class-catalog") return route.fulfill({ json: [schoolClass] });
    if (url.pathname === `/api/classes/${schoolClass.id}/sheet`) {
      if (url.searchParams.get("semester") !== "2") return route.fulfill({ json: sheet(1) });
      await secondSheetHold;
      return route.fulfill({ status: 500, json: { detail: "synthetic failure" } }).catch(() => {});
    }
    if (url.pathname === "/api/reports/class-sheets") {
      pdfRequests.push(url.search);
      await pdfHold;
      return route
        .fulfill({ status: 200, contentType: "application/pdf", body: "%PDF-1.4\n%%EOF\n" })
        .catch(() => {});
    }
    return route.fulfill({ json: [] });
  });
  return pdfRequests;
}

test("the PDF leave guard stays while a semester change reloads or fails the class report", async ({
  page,
}) => {
  const pdfHold = Promise.withResolvers<void>();
  const secondSheetHold = Promise.withResolvers<void>();
  const pdfRequests = await mockApi(page, pdfHold.promise, secondSheetHold.promise);
  const dialog = page.getByRole("dialog");
  const leaveTitle = dialog.getByRole("heading", { name: "Leave this page?" });
  const allClasses = page.getByRole("link", { name: "All classes", exact: true });
  const reportUrl = new RegExp(`/class-report/${schoolClass.id}\\?semester=2$`);

  await page.goto(`${teacherOrigin}/class-report/${schoolClass.id}?semester=1`);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("5/A");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  await expect.poll(() => pdfRequests.length).toBe(1);

  // Another semester stays on the page and loads its sheet while the PDF is still on its way.
  const secondSheet = page.waitForRequest((request) =>
    request.url().includes(`/api/classes/${schoolClass.id}/sheet?semester=2`),
  );
  await page.getByRole("radio", { name: "S2", exact: true }).click();
  await secondSheet;
  await expect(page).toHaveURL(reportUrl);
  await expect(page.getByRole("heading", { level: 1 })).toBeHidden();

  await allClasses.click();
  await expect(leaveTitle).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await expect(page).toHaveURL(reportUrl);

  // The sheet fails to load; the PDF is still being prepared, so leaving still asks first.
  secondSheetHold.resolve();
  await expect(page.getByText("The data could not be loaded.")).toBeVisible();
  await allClasses.click();
  await expect(leaveTitle).toBeVisible();
  await expect(page).toHaveURL(reportUrl);

  pdfHold.resolve();
});
