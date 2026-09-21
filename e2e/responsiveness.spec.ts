import { expect, test } from "@playwright/test";
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

test("slow PDF actions stay disabled, show progress, and restore when ready", async ({
  browser,
}) => {
  const context = await authenticatedContext(browser, adminEmail);
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const page = await context.newPage();

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
          subjects: [
            {
              subject: "english",
              student_count: 22,
              column_count: 14,
              owner_roles: ["main"],
              my_roles: [],
              can_write: !archived,
            },
          ],
        },
      ],
    });
  });
  let pdfCompleted = false;
  const pdfQueries: URLSearchParams[] = [];
  await page.route("**/api/reports/pdf**", async (route) => {
    pdfQueries.push(new URL(route.request().url()).searchParams);
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.fulfill({
      status: 200,
      contentType: "application/pdf",
      body: minimalPdf(),
    });
    pdfCompleted = true;
  });

  await page.goto(`${adminOrigin}/admin/reports`);
  const generate = page.getByRole("button", { name: "Open PDF set" }).first();
  await expect(generate).toBeEnabled();

  const popupPromise = page.waitForEvent("popup");
  await generate.click();
  const popup = await popupPromise;

  await expect(generate).toBeDisabled();
  await expect(generate).toHaveAttribute("data-pending", "true");
  await expect(page.getByText("Generating PDF…").last()).toBeVisible();
  await expect(generate).toBeEnabled();
  await expect(generate).not.toHaveAttribute("data-pending", "true");
  await expect(page.getByText("PDF is ready in the new tab.")).toBeVisible();
  expect(pdfCompleted).toBe(true);
  expect(popup.isClosed()).toBe(false);
  expect(pdfQueries[0].get("semester_id")).toBe("71");
  expect(pdfQueries[0].get("class_id")).toBe("31");

  await page.getByLabel("Academic year", { exact: true }).first().selectOption("42");
  await page.getByRole("radio", { name: "S2", exact: true }).click();
  await expect(page.getByLabel("Class", { exact: true }).first()).toHaveValue("32");
  await expect(generate).toBeEnabled();
  await generate.click();
  await expect.poll(() => pdfQueries.length).toBe(2);
  expect(pdfQueries[1].get("semester_id")).toBe("82");
  expect(pdfQueries[1].get("class_id")).toBe("32");
  await expect(generate).toBeEnabled();

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
