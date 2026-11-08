import { expect, test, type Browser, type Page, type Route } from "@playwright/test";
import { authenticatedContext } from "./helpers/auth";
import { adminOrigin } from "./helpers/origins";

const adminEmail = process.env.E2E_ADMIN_EMAIL ?? "admin@example-school.k12.tr";

function minimalPdf(): Buffer {
  const header = "%PDF-1.4\n";
  const objects = [
    "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
    "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
    "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>\nendobj\n",
  ];
  const offsets: number[] = [];
  let body = header;
  for (const object of objects) {
    offsets.push(Buffer.byteLength(body));
    body += object;
  }
  const xrefOffset = Buffer.byteLength(body);
  const xref = offsets.map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`).join("");
  return Buffer.from(
    `${body}xref\n0 4\n0000000000 65535 f \n${xref}trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`,
  );
}

const ELEMENTARY = "Elementary English report cards";
const CLASS_FILE = "3-A İngilizce Karne 2026-2027 1. Dönem.pdf";
const SCHOOL_ZIP = "Tüm Okul İngilizce Karne 2026-2027 1. Dönem.zip";

/** Two primary classes get the elementary English card; German has one taker in 3/A. */
const ROSTER: Record<string, unknown[]> = {
  english_elementary: [
    {
      id: 31,
      name: "3/A",
      grade_level: 3,
      students: [
        { id: 501, full_name: "Ali Yılmaz", school_number: 11 },
        { id: 502, full_name: "Ayşe Kaya", school_number: 12 },
      ],
    },
    {
      id: 41,
      name: "4/B",
      grade_level: 4,
      students: [
        { id: 601, full_name: "Can Demir", school_number: 21 },
        { id: 602, full_name: "Deniz Ak", school_number: 22 },
      ],
    },
  ],
  german_karne: [
    {
      id: 31,
      name: "3/A",
      grade_level: 3,
      students: [{ id: 502, full_name: "Ayşe Kaya", school_number: 12 }],
    },
  ],
};

function reportCard(page: Page, title: string) {
  return page
    .locator('[data-slot="card"]')
    .filter({ has: page.getByRole("heading", { name: title, exact: true }) });
}

type Job = Record<string, unknown> & { id: number; status: string };

/**
 * The report centre's API: academic years, the picker roster, direct PDFs (answered when `hold`
 * resolves, or at once) and report jobs that advance one step on every downloads-list poll.
 */
async function mockReportApi(page: Page, hold?: Promise<void>) {
  const pdfQueries: URLSearchParams[] = [];
  const jobBodies: Record<string, unknown>[] = [];
  const jobs: Job[] = [];
  const pdfResponses: ((route: Route) => Promise<void>)[] = [];
  await page.route("**/api/academic-years", (route) =>
    route.fulfill({
      json: [
        {
          id: 41,
          label: "2026-2027",
          status: "active",
          semesters: [
            { id: 71, number: 1, status: "open" },
            { id: 72, number: 2, status: "locked" },
          ],
        },
      ],
    }),
  );
  await page.route("**/api/reports/roster**", (route) => {
    const kind = new URL(route.request().url()).searchParams.get("kind") ?? "";
    return route.fulfill({ json: ROSTER[kind] ?? [] });
  });
  await page.route("**/api/reports/pdf**", async (route) => {
    pdfQueries.push(new URL(route.request().url()).searchParams);
    const custom = pdfResponses.shift();
    if (custom) return custom(route);
    await hold;
    await route
      .fulfill({
        status: 200,
        contentType: "application/pdf",
        headers: {
          "Content-Disposition": `inline; filename="3-A Ingilizce Karne 2026-2027 1. Donem.pdf"; filename*=UTF-8''${encodeURIComponent(CLASS_FILE)}`,
        },
        body: minimalPdf(),
      })
      .catch(() => undefined);
  });
  await page.route("**/api/reports/jobs", async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    jobBodies.push(body);
    const job: Job = {
      id: 900 + jobBodies.length,
      kind: "report_set",
      status: "queued",
      progress: 0,
      total: 2,
      output_filename: (body.student_ids as number[]).length
        ? "Seçili Öğrenciler İngilizce Karne 2026-2027 1. Dönem.zip"
        : SCHOOL_ZIP,
      output_size: null,
      output_expires_at: null,
      error_code: null,
      created_at: "2026-11-07T09:00:00",
      parent_id: null,
      part: null,
    };
    jobs.unshift(job);
    await route.fulfill({ status: 202, json: job });
  });
  await page.route(/\/api\/jobs(\?.*)?$/, (route) => {
    const listed = jobs.map((job) => ({ ...job }));
    for (const job of jobs) {
      if (job.status === "queued") Object.assign(job, { status: "running", progress: 1 });
      else if (job.status === "running") {
        Object.assign(job, {
          status: "succeeded",
          progress: 2,
          output_size: 2_400_000,
          output_expires_at: "2099-01-01T09:00:00",
        });
      }
    }
    return route.fulfill({ json: listed });
  });
  return { pdfQueries, jobBodies, pdfResponses, jobs };
}

async function openReportCentre(browser: Browser, hold?: Promise<void>) {
  const context = await authenticatedContext(browser, adminEmail);
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const page = await context.newPage();
  const api = await mockReportApi(page, hold);
  const popups: Page[] = [];
  page.on("popup", (popup) => popups.push(popup));
  await page.goto(`${adminOrigin}/admin/reports`);
  return { context, page, api, popups };
}

test("one class opens in a tab opened during the click and downloads under its server name", async ({
  browser,
}) => {
  const { context, page, api, popups } = await openReportCentre(browser);
  const card = reportCard(page, ELEMENTARY);
  await expect(card.getByLabel("Class", { exact: true })).toHaveValue("31");

  // The tab opens synchronously with the click, before the PDF exists (pop-up blockers only
  // allow that), then receives the PDF. Headless Chromium has no PDF viewer and turns that
  // navigation into a download; a headed browser shows the blob URL.
  const pdfReady = Promise.withResolvers<void>();
  api.pdfResponses.push(async (route) => {
    await pdfReady.promise;
    await route.fulfill({
      status: 200,
      contentType: "application/pdf",
      headers: {
        "Content-Disposition": `inline; filename*=UTF-8''${encodeURIComponent(CLASS_FILE)}`,
      },
      body: minimalPdf(),
    });
  });
  const [popup] = await Promise.all([
    page.waitForEvent("popup"),
    card.getByRole("button", { name: "View", exact: true }).click(),
  ]);
  expect(popup.url()).toBe("about:blank");
  const delivered = Promise.race([
    popup.waitForEvent("download").then(() => "download"),
    // In headless Chromium the blob navigation is aborted in favour of the download.
    popup.waitForURL(/^blob:/).then(
      () => "blob",
      () => new Promise<string>(() => undefined),
    ),
  ]);
  pdfReady.resolve();
  expect(["download", "blob"]).toContain(await delivered);
  expect(api.pdfQueries[0].get("class_id")).toBe("31");
  expect(api.pdfQueries[0].get("semester_id")).toBe("71");

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    card.getByRole("button", { name: "Download", exact: true }).click(),
  ]);
  expect(download.suggestedFilename()).toBe(CLASS_FILE);
  expect(popups).toHaveLength(1);

  // A rate-limited request says how long to wait.
  api.pdfResponses.push((route) =>
    route.fulfill({
      status: 429,
      headers: { "Retry-After": "12" },
      json: { detail: { code: "rate_limited" } },
    }),
  );
  await card.getByRole("button", { name: "Download", exact: true }).click();
  await expect(
    page.getByText("Too many requests in one minute. Try again in 12 seconds."),
  ).toBeVisible();

  await context.close();
});

test("the whole school becomes a job whose progress and file appear in Downloads", async ({
  browser,
}) => {
  const { context, page, api } = await openReportCentre(browser);
  const card = reportCard(page, ELEMENTARY);
  await expect(card.getByText("Whole school · 4 students")).toBeVisible();
  await card.getByRole("radio", { name: "ZIP per class", exact: true }).click();
  await card.getByRole("button", { name: "Prepare whole school", exact: true }).click();
  await expect(page.getByText(/^Preparing\. The file will appear in Downloads/)).toBeVisible();
  expect(api.jobBodies).toEqual([
    {
      semester_id: 71,
      kind: "english_elementary",
      locale: "tr",
      format: "per_class",
      class_ids: [],
      student_ids: [],
    },
  ]);

  const downloads = page
    .locator('[data-slot="card"]')
    .filter({ has: page.getByText("Downloads", { exact: true }) });
  const row = downloads.getByRole("listitem").filter({ hasText: SCHOOL_ZIP });
  await expect(row.getByText("Class 1/2")).toBeVisible();
  await expect(row.getByText("Ready", { exact: true })).toBeVisible({ timeout: 10_000 });
  // The base-ui Button renders the link with the button role.
  await expect(row.locator('a[href="/api/jobs/901/download"]')).toBeVisible();
  await expect(page.getByText(`${SCHOOL_ZIP} is ready.`)).toBeVisible();

  await context.close();
});

test("the student picker keeps ticks across classes and sends a mixed selection as a job", async ({
  browser,
}) => {
  const { context, page, api } = await openReportCentre(browser);
  await reportCard(page, ELEMENTARY).getByRole("button", { name: "Choose students" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: /Choose students/ })).toBeVisible();

  await dialog.getByRole("checkbox", { name: "Ali Yılmaz" }).click();
  await expect(dialog.getByText("Selected: 1")).toBeVisible();
  await expect(dialog.getByText("The file downloads at once.")).toBeVisible();

  await dialog.getByRole("button", { name: "4/B", exact: true }).click();
  await dialog.getByRole("checkbox", { name: "All of 4/B" }).click();
  await expect(dialog.getByText("Selected: 3")).toBeVisible();
  await expect(dialog.getByRole("checkbox", { name: "Deniz Ak" })).toBeChecked();

  // Search reaches every class; the earlier tick is still there.
  await dialog.getByRole("searchbox").fill("ali");
  await expect(dialog.getByRole("checkbox", { name: "Ali Yılmaz" })).toBeChecked();
  await dialog.getByRole("searchbox").fill("");

  await expect(
    dialog.getByText("Prepared in the background and added to Downloads."),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Prepare", exact: true }).click();
  await expect(dialog).toBeHidden();
  expect(api.jobBodies).toEqual([
    {
      semester_id: 71,
      kind: "english_elementary",
      locale: "tr",
      format: "combined",
      class_ids: [],
      student_ids: [501, 601, 602],
    },
  ]);

  await context.close();
});

test("leaving while a direct PDF downloads asks first, then stops the request", async ({
  browser,
}) => {
  const hold = Promise.withResolvers<void>();
  const { context, page, api } = await openReportCentre(browser, hold.promise);
  const download = reportCard(page, ELEMENTARY).getByRole("button", {
    name: "Download",
    exact: true,
  });
  const classTables = page.getByRole("link", { name: "Class tables", exact: true });
  const dialog = page.getByRole("dialog");
  const cancel = dialog.getByRole("button", { name: "Cancel" });
  const leave = dialog.getByRole("button", { name: /^Leave/ });

  await download.click();
  await expect(download).toHaveAttribute("data-pending", "true");
  await expect.poll(() => api.pdfQueries.length).toBe(1);

  // Following the link to the page already open leaves nothing: no dialog.
  await page.getByRole("link", { name: "Report centre", exact: true }).click();
  await expect(page).toHaveURL(`${adminOrigin}/admin/reports`);
  await expect(download).toHaveAttribute("data-pending", "true");

  await classTables.click();
  await expect(dialog.getByRole("heading", { name: "Leave this page?" })).toBeVisible();
  await expect(leave).toBeDisabled();
  await cancel.click();
  await expect(dialog).toBeHidden();
  await expect(download).toHaveAttribute("data-pending", "true");

  await classTables.click();
  await expect(leave).toHaveText("Leave", { timeout: 6000 });
  const aborted = page.waitForEvent("requestfailed", (request) =>
    request.url().includes("/api/reports/pdf"),
  );
  await leave.click();
  await expect(page).toHaveURL(`${adminOrigin}/admin/classes`);
  await aborted;
  hold.resolve();

  await context.close();
});

test("a set split into numbered parts lists each part with its own download", async ({
  browser,
}) => {
  const { context, page, api } = await openReportCentre(browser);
  const done = {
    kind: "report_set",
    status: "succeeded",
    progress: 29,
    total: 29,
    output_size: 300_000_000,
    output_expires_at: "2099-01-01T09:00:00",
    error_code: null,
    created_at: "2026-11-07T09:00:00",
  };
  const part = (number: number) => ({
    ...done,
    id: 700 + number,
    parent_id: 700,
    part: number,
    output_size: 150_000_000,
    output_filename: SCHOOL_ZIP.replace(".zip", ` (Bölüm ${number}).zip`),
  });
  api.jobs.push(part(2), part(1), {
    ...done,
    id: 700,
    parent_id: null,
    part: null,
    output_filename: SCHOOL_ZIP,
  });
  await page.reload();

  const downloads = page
    .locator('[data-slot="card"]')
    .filter({ has: page.getByText("Downloads", { exact: true }) });
  const parts = downloads.getByRole("list", { name: `Parts of ${SCHOOL_ZIP}` });
  await expect(parts.getByRole("listitem")).toHaveText([/\(Bölüm 1\)\.zip/, /\(Bölüm 2\)\.zip/]);
  await expect(parts.locator('a[href="/api/jobs/701/download"]')).toBeVisible();
  await expect(parts.locator('a[href="/api/jobs/702/download"]')).toBeVisible();
  // The request itself has no single file to download.
  await expect(downloads.locator('a[href="/api/jobs/700/download"]')).toHaveCount(0);
  await expect(downloads.getByText("2 parts", { exact: false })).toBeVisible();

  await context.close();
});

test("a job that failed because its classes or pupils changed asks for a fresh selection", async ({
  browser,
}) => {
  const { context, page, api } = await openReportCentre(browser);
  const failed = (id: number, code: string) => ({
    id,
    kind: "report_set",
    status: "failed",
    progress: 0,
    total: 2,
    output_filename: SCHOOL_ZIP,
    output_size: null,
    output_expires_at: null,
    error_code: code,
    created_at: "2026-11-07T09:00:00",
    parent_id: null,
    part: null,
  });
  // A pupil moved while the job ran; a chosen class lost every pupil before it started.
  api.jobs.push(failed(802, "report_roster_changed"), failed(801, "class_not_in_report_set"));
  await page.reload();

  const downloads = page
    .locator('[data-slot="card"]')
    .filter({ has: page.getByText("Downloads", { exact: true }) });
  await expect(
    downloads.getByText(
      "The selection is out of date: a class or student list has changed. Reload the page and try again.",
    ),
  ).toHaveCount(2);

  await context.close();
});
