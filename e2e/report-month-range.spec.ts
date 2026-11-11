import { expect, test, type Browser, type Locator, type Page } from "@playwright/test";
import { authenticatedContext } from "./helpers/auth";
import { adminOrigin } from "./helpers/origins";

const adminEmail = process.env.E2E_ADMIN_EMAIL ?? "admin@example-school.k12.tr";
const MIDDLE = "Middle school English report cards";
const ELEMENTARY = "Elementary English report cards";

function reportCard(page: Page, title: string) {
  return page
    .locator('[data-slot="card"]')
    .filter({ has: page.getByRole("heading", { name: title, exact: true }) });
}

async function openReports(browser: Browser) {
  const context = await authenticatedContext(browser, adminEmail);
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const page = await context.newPage();
  const pdfQueries: URLSearchParams[] = [];
  const jobBodies: Record<string, unknown>[] = [];
  await page.route("**/api/academic-years", (route) =>
    route.fulfill({
      json: [
        {
          id: 41,
          label: "2026-2027",
          status: "active",
          semesters: [{ id: 71, number: 1, status: "open" }],
        },
      ],
    }),
  );
  await page.route("**/api/reports/roster**", (route) => {
    const kind = new URL(route.request().url()).searchParams.get("kind");
    return route.fulfill({
      json:
        kind === "english_middle"
          ? [
              {
                id: 51,
                name: "5/A",
                grade_level: 5,
                students: [
                  { id: 501, full_name: "Synthetic Pupil One", school_number: 11 },
                  { id: 502, full_name: "Synthetic Pupil Two", school_number: 12 },
                ],
              },
              {
                id: 61,
                name: "6/B",
                grade_level: 6,
                students: [{ id: 601, full_name: "Synthetic Pupil Three", school_number: 21 }],
              },
            ]
          : kind === "english_elementary"
            ? [
                {
                  id: 31,
                  name: "3/A",
                  grade_level: 3,
                  students: [{ id: 301, full_name: "Synthetic Primary Pupil", school_number: 31 }],
                },
              ]
            : [],
    });
  });
  await page.route("**/api/reports/pdf**", (route) => {
    pdfQueries.push(new URL(route.request().url()).searchParams);
    return route.fulfill({
      contentType: "application/pdf",
      headers: { "Content-Disposition": 'attachment; filename="synthetic-report.pdf"' },
      body: Buffer.from("%PDF-1.4\n%%EOF\n"),
    });
  });
  await page.route("**/api/reports/jobs", (route) => {
    jobBodies.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({
      status: 202,
      json: {
        id: 900 + jobBodies.length,
        kind: "report_set",
        status: "queued",
        progress: 0,
        total: 2,
        output_filename: "synthetic-report.pdf",
        output_size: null,
        output_expires_at: null,
        error_code: null,
        created_at: "2026-11-11T09:00:00",
        parent_id: null,
        part: null,
      },
    });
  });
  await page.route(/\/api\/jobs(\?.*)?$/, (route) => route.fulfill({ json: [] }));
  await page.goto(`${adminOrigin}/admin/reports`);
  const middle = reportCard(page, MIDDLE);
  await expect(middle.getByLabel("Class", { exact: true })).toHaveValue("51");
  return { context, page, middle, pdfQueries, jobBodies };
}

async function chooseMonth(page: Page, card: Locator, edge: "Starting" | "Ending", month: string) {
  await card.getByRole("button", { name: new RegExp(`^${edge} month:`) }).click();
  const calendar = page.getByRole("dialog", { name: `${edge} month`, exact: true });
  await expect(calendar.getByRole("button", { name: "January", exact: true })).toBeVisible();
  await expect(calendar.getByRole("button", { name: "December", exact: true })).toBeVisible();
  await calendar.getByRole("button", { name: month, exact: true }).click();
  await expect(calendar).toBeHidden();
  await expect(
    card.getByRole("button", { name: `${edge} month: ${month}`, exact: true }),
  ).toBeVisible();
}

async function download(page: Page, container: Locator) {
  const [file] = await Promise.all([
    page.waitForEvent("download"),
    container.getByRole("button", { name: "Download", exact: true }).click(),
  ]);
  expect(file.suggestedFilename()).toBe("synthetic-report.pdf");
}

test("middle cards send the selected month range for class and student downloads only", async ({
  browser,
}) => {
  const { context, page, middle, pdfQueries } = await openReports(browser);
  await expect(middle.getByRole("button", { name: "Starting month: September" })).toBeVisible();
  await expect(middle.getByRole("button", { name: "Ending month: November" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Starting month:/ })).toHaveCount(1);
  await middle.getByRole("button", { name: "Starting month: September" }).click();
  const calendar = page.getByRole("dialog", { name: "Starting month", exact: true });
  await expect(calendar.getByRole("button", { name: "September", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await calendar.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(calendar).toBeHidden();

  await download(page, middle);
  expect(pdfQueries[0].get("start_month")).toBe("9");
  expect(pdfQueries[0].get("end_month")).toBe("11");

  // A period can cross New Year; the academic semester still selects the grades.
  await chooseMonth(page, middle, "Starting", "December");
  await chooseMonth(page, middle, "Ending", "February");
  await download(page, middle);
  expect(Object.fromEntries(pdfQueries[1])).toMatchObject({
    semester_id: "71",
    kind: "english_middle",
    class_id: "51",
    start_month: "12",
    end_month: "2",
  });

  await middle.getByRole("button", { name: "Choose students" }).click();
  const picker = page.getByRole("dialog");
  await picker.getByRole("checkbox", { name: "Synthetic Pupil One" }).click();
  await download(page, picker);
  await expect(picker).toBeHidden();
  expect(pdfQueries[2].getAll("student_id")).toEqual(["501"]);
  expect(pdfQueries[2].has("class_id")).toBe(false);
  expect(pdfQueries[2].get("start_month")).toBe("12");
  expect(pdfQueries[2].get("end_month")).toBe("2");

  await download(page, reportCard(page, ELEMENTARY));
  expect(pdfQueries[3].get("kind")).toBe("english_elementary");
  expect(pdfQueries[3].has("start_month")).toBe(false);
  expect(pdfQueries[3].has("end_month")).toBe(false);
  await context.close();
});

test("every background format and a mixed student selection keep the chosen months", async ({
  browser,
}) => {
  const { context, page, middle, jobBodies } = await openReports(browser);
  await chooseMonth(page, middle, "Starting", "November");
  await chooseMonth(page, middle, "Ending", "January");
  const formats = [
    ["One PDF", "combined"],
    ["ZIP per class", "per_class"],
    ["ZIP per student", "per_student"],
  ] as const;
  for (const [index, [label, format]] of formats.entries()) {
    await middle.getByRole("radio", { name: label, exact: true }).click();
    await middle.getByRole("button", { name: "Prepare whole school", exact: true }).click();
    await expect.poll(() => jobBodies.length).toBe(index + 1);
    expect(jobBodies[index]).toMatchObject({
      semester_id: 71,
      kind: "english_middle",
      format,
      class_ids: [],
      student_ids: [],
      start_month: 11,
      end_month: 1,
    });
  }

  await chooseMonth(page, middle, "Starting", "December");
  await chooseMonth(page, middle, "Ending", "February");
  await middle.getByRole("button", { name: "Choose students" }).click();
  const picker = page.getByRole("dialog");
  await picker.getByRole("checkbox", { name: "Synthetic Pupil One" }).click();
  await picker.getByRole("button", { name: "6/B", exact: true }).click();
  await picker.getByRole("checkbox", { name: "Synthetic Pupil Three" }).click();
  await picker.getByRole("button", { name: "Prepare", exact: true }).click();
  await expect(picker).toBeHidden();
  expect(jobBodies[3]).toMatchObject({
    semester_id: 71,
    kind: "english_middle",
    format: "combined",
    class_ids: [],
    student_ids: [501, 601],
    start_month: 12,
    end_month: 2,
  });
  // Editing the next request does not alter the periods already queued.
  expect(jobBodies.slice(0, 3).map((body) => [body.start_month, body.end_month])).toEqual([
    [11, 1],
    [11, 1],
    [11, 1],
  ]);
  await context.close();
});
