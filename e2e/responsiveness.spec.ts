import { expect, test, type Browser, type Page } from "@playwright/test";
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
const GERMAN = "German report cards";

/** One report card on the Report centre, found by its set title. */
function reportCard(page: Page, title: string) {
  return page
    .locator('[data-slot="card"]')
    .filter({ has: page.getByRole("heading", { name: title, exact: true }) });
}

/**
 * Two academic years with one grade-3 class each. Every class has English and German students,
 * so the elementary English and German sets are both eligible.
 */
async function mockReportCatalog(page: Page) {
  await page.route("**/api/academic-years", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 41,
          label: "2026-2027",
          status: "active",
          semesters: [
            { id: 71, number: 1, status: "open" },
            { id: 72, number: 2, status: "locked" },
          ],
        },
        {
          id: 42,
          label: "2023-2024",
          status: "archived",
          semesters: [
            { id: 81, number: 1, status: "locked" },
            { id: 82, number: 2, status: "locked" },
          ],
        },
      ]),
    });
  });
  await page.route("**/api/class-catalog**", async (route) => {
    const archived = new URL(route.request().url()).searchParams.get("year_id") === "42";
    await route.fulfill({
      json: [
        {
          id: archived ? 32 : 31,
          name: archived ? "3/B" : "3/A",
          grade_level: 3,
          section: archived ? "B" : "A",
          subjects: ["english", "german"].map((subject) => ({
            subject,
            student_count: 22,
            column_count: 14,
            owner_roles: ["main"],
            my_roles: [],
            can_write: !archived,
          })),
        },
      ],
    });
  });
}

function delay(ms: number) {
  const { promise, resolve } = Promise.withResolvers<void>();
  setTimeout(resolve, ms);
  return promise;
}

/**
 * Answers `/api/reports/pdf` slowly: after 1.5 s, or when `hold` resolves if one is given.
 * `events` records each request's start and end in order, so tests can assert sequencing.
 */
async function mockSlowPdf(page: Page, hold?: Promise<void>) {
  const queries: URLSearchParams[] = [];
  const events: string[] = [];
  const handled: Promise<void>[] = [];
  await page.route("**/api/reports/pdf**", (route) => {
    const query = new URL(route.request().url()).searchParams;
    const kind = query.get("kind");
    queries.push(query);
    events.push(`start ${kind}`);
    const done = (async () => {
      await (hold ?? delay(1500));
      events.push(`end ${kind}`);
      await route
        .fulfill({ status: 200, contentType: "application/pdf", body: minimalPdf() })
        .catch(() => events.push(`abandoned ${kind}`));
    })();
    handled.push(done);
    return done;
  });
  return { queries, events, handled };
}

async function openReportCentre(browser: Browser, hold?: Promise<void>) {
  const context = await authenticatedContext(browser, adminEmail);
  await context.addInitScript(() => {
    localStorage.setItem("i18nextLng", "en");
    // Records every window.open URL. Setting data-block-next-popup makes the next call behave
    // like a blocked popup.
    const openedUrls: string[] = [];
    Object.defineProperty(window, "openedUrls", { value: openedUrls });
    const open = window.open.bind(window);
    window.open = (...args: Parameters<typeof window.open>) => {
      openedUrls.push(String(args[0]));
      const root = document.documentElement;
      if (root.dataset.blockNextPopup === undefined) return open(...args);
      delete root.dataset.blockNextPopup;
      return null;
    };
  });
  const page = await context.newPage();
  await mockReportCatalog(page);
  const pdf = await mockSlowPdf(page, hold);
  const popups: Page[] = [];
  page.on("popup", (popup) => popups.push(popup));
  await page.goto(`${adminOrigin}/admin/reports`);
  const openedUrls = () => page.evaluate(() => Reflect.get(window, "openedUrls") as string[]);
  return { context, page, pdf, popups, openedUrls };
}

test("PDF sets default to all classes and open a tab only once the PDF is ready", async ({
  browser,
}) => {
  const { context, page, pdf, popups, openedUrls } = await openReportCentre(browser);
  const card = reportCard(page, ELEMENTARY);
  const classSelect = card.getByLabel("Class", { exact: true });
  const generate = card.getByRole("button");
  await expect(classSelect).toHaveValue("0");
  await expect(generate).toBeEnabled();

  await generate.click();
  await expect(generate).toHaveAttribute("data-pending", "true");
  await expect(generate).toBeDisabled();
  await expect(card.getByRole("status")).toHaveText("Generating PDF…");
  expect(popups).toHaveLength(0);

  await page.waitForEvent("popup");
  expect(pdf.events).toEqual(["start english_elementary", "end english_elementary"]);
  expect(await openedUrls()).toEqual([expect.stringMatching(/^blob:/)]);
  await expect(generate).toBeEnabled();
  await expect(generate).not.toHaveAttribute("data-pending", "true");
  expect(pdf.queries[0].get("semester_id")).toBe("71");
  expect(pdf.queries[0].has("class_id")).toBe(false);

  await page.getByLabel("Academic year", { exact: true }).first().selectOption("42");
  await page.getByRole("radio", { name: "S2", exact: true }).click();
  await expect(classSelect).toHaveValue("0");
  await expect(generate).toBeEnabled();
  await Promise.all([page.waitForEvent("popup"), generate.click()]);
  expect(pdf.queries[1].get("semester_id")).toBe("82");
  expect(pdf.queries[1].has("class_id")).toBe(false);

  await expect(generate).toBeEnabled();
  await classSelect.selectOption("32");
  await page.evaluate(() => {
    document.documentElement.dataset.blockNextPopup = "";
  });
  const popupsBeforeBlocked = popups.length;
  await generate.click();
  await expect(page.getByText("The PDF is ready.")).toBeVisible();
  expect(popups).toHaveLength(popupsBeforeBlocked);
  expect(pdf.queries[2].get("semester_id")).toBe("82");
  expect(pdf.queries[2].get("class_id")).toBe("32");
  await Promise.all([
    page.waitForEvent("popup"),
    page.getByRole("button", { name: "Open PDF", exact: true }).click(),
  ]);
  const [, , blocked, reopened] = await openedUrls();
  expect(blocked).toMatch(/^blob:/);
  expect(reopened).toBe(blocked);

  await context.close();
});

test("PDF sets queue behind the running one and open in request order", async ({ browser }) => {
  const { context, page, pdf, popups } = await openReportCentre(browser);
  const elementary = reportCard(page, ELEMENTARY);
  const german = reportCard(page, GERMAN);
  await expect(elementary.getByRole("button")).toBeEnabled();
  await expect(german.getByRole("button")).toBeEnabled();

  await elementary.getByRole("button").click();
  await expect(elementary.getByRole("button")).toHaveAttribute("data-pending", "true");
  await expect(german.getByRole("button")).toBeEnabled();
  await german.getByRole("button").click();
  await expect(german.getByRole("button")).toBeDisabled();
  await expect(german.getByRole("button")).toHaveText("Queued");
  await expect(german.getByRole("button")).not.toHaveAttribute("data-pending", "true");
  await expect(elementary.getByRole("status")).toHaveText("Generating PDF…");
  expect(pdf.events).toEqual(["start english_elementary"]);

  await expect(elementary.getByRole("button")).not.toHaveAttribute("data-pending", "true");
  await expect(german.getByRole("button")).toHaveAttribute("data-pending", "true");
  await expect(german.getByRole("status")).toHaveText("Generating PDF…");
  await expect(german.getByRole("button")).not.toHaveAttribute("data-pending", "true");
  await expect.poll(() => popups.length).toBe(2);
  expect(pdf.events).toEqual([
    "start english_elementary",
    "end english_elementary",
    "start german_karne",
    "end german_karne",
  ]);

  await context.close();
});

test("leaving while a PDF set generates asks first, then stops the request", async ({
  browser,
}) => {
  const hold = Promise.withResolvers<void>();
  const { context, page, pdf, popups } = await openReportCentre(browser, hold.promise);
  const generate = reportCard(page, ELEMENTARY).getByRole("button");
  const classTables = page.getByRole("link", { name: "Class tables", exact: true });
  const dialog = page.getByRole("dialog");
  const cancel = dialog.getByRole("button", { name: "Cancel" });
  const leave = dialog.getByRole("button", { name: /^Leave/ });

  await generate.click();
  await expect(generate).toHaveAttribute("data-pending", "true");
  await expect.poll(() => pdf.events).toEqual(["start english_elementary"]);

  await classTables.click();
  await expect(dialog.getByRole("heading", { name: "Leave this page?" })).toBeVisible();
  await expect(cancel).toBeEnabled();
  await expect(leave).toHaveText(/^Leave \(\d\)$/);
  await expect(leave).toBeDisabled();
  await cancel.click();
  await expect(dialog).toBeHidden();
  await expect(page).toHaveURL(`${adminOrigin}/admin/reports`);
  await expect(generate).toHaveAttribute("data-pending", "true");

  await classTables.click();
  await expect(leave).toBeDisabled();
  await expect(leave).toHaveText("Leave", { timeout: 6000 });
  await expect(leave).toBeEnabled();
  const aborted = page.waitForEvent("requestfailed", (request) =>
    request.url().includes("/api/reports/pdf"),
  );
  await leave.click();
  await expect(page).toHaveURL(`${adminOrigin}/admin/classes`);
  await aborted;

  hold.resolve();
  await Promise.all(pdf.handled);
  expect(pdf.queries).toHaveLength(1);
  expect(popups).toHaveLength(0);

  await context.close();
});

test("destructive user actions use the styled site dialog", async ({ browser }) => {
  const context = await authenticatedContext(browser, adminEmail);
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const page = await context.newPage();

  await page.goto(`${adminOrigin}/admin/users`);
  await page.getByRole("button", { name: "Deactivate", exact: true }).first().click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "Deactivate" })).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();

  await context.close();
});
