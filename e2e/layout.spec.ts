import { expect, test } from "@playwright/test";
import { authenticatedContext } from "./helpers/auth";
import { adminOrigin, teacherOrigin } from "./helpers/origins";
import { expectContainedTable, expectFocusedTable } from "./helpers/table";

const adminEmail = process.env.E2E_ADMIN_EMAIL ?? "admin@example-school.k12.tr";

test("class tables contain overflow and focused grade pages keep readable context", async ({
  browser,
}) => {
  const context = await authenticatedContext(browser, adminEmail);
  const admin = await context.newPage();
  await admin.setViewportSize({ width: 768, height: 900 });
  await admin.goto(`${adminOrigin}/admin/classes`);

  const rosterSurface = admin.getByTestId("class-roster-surface");
  await expectContainedTable(rosterSurface);

  const mainBefore = await admin.locator("#main").boundingBox();
  await admin.getByRole("button", { name: /Minimize side panel|Yan paneli küçült/ }).click();
  const mainAfter = await admin.locator("#main").boundingBox();
  expect(mainBefore).not.toBeNull();
  expect(mainAfter).not.toBeNull();
  expect(mainAfter!.width).toBeGreaterThan(mainBefore!.width + 100);
  await admin.getByRole("button", { name: /Restore side panel|Yan paneli geri getir/ }).click();

  const lastDragHandle = rosterSurface.locator('button[draggable="true"]').last();
  await lastDragHandle.scrollIntoViewIfNeeded();
  await admin.evaluate(() => window.scrollBy(0, 240));
  const handleBox = await lastDragHandle.boundingBox();
  expect(handleBox).not.toBeNull();
  const startY = await admin.evaluate(() => window.scrollY);
  await admin.mouse.move(handleBox!.x + handleBox!.width / 2, handleBox!.y + handleBox!.height / 2);
  await admin.mouse.down();
  await admin.mouse.move(handleBox!.x + handleBox!.width / 2 + 8, handleBox!.y + 4, { steps: 4 });
  await admin.mouse.move(20, 4, { steps: 12 });
  await expect.poll(() => admin.evaluate(() => window.scrollY)).toBeLessThan(startY);
  await admin.mouse.up();

  const catalogResponse = await context.request.get(`${teacherOrigin}/api/class-catalog`);
  expect(catalogResponse.ok()).toBeTruthy();
  const catalog = (await catalogResponse.json()) as Array<{
    id: number;
    subjects: Array<{ subject: string }>;
  }>;
  const board = catalog.find((item) =>
    item.subjects.some((subject) => subject.subject === "english"),
  );
  expect(board).toBeTruthy();

  const teacher = await context.newPage();
  await teacher.setViewportSize({ width: 768, height: 900 });
  await teacher.goto(`${teacherOrigin}/classes/${board!.id}/english`);
  const gradeSurface = teacher.getByTestId("grade-grid-surface");
  await expectFocusedTable(gradeSurface);

  await context.close();
});
