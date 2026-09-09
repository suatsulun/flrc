import { expect, test } from "@playwright/test";
import { authenticatedContext } from "./helpers/auth";
import { expectFocusedTable } from "./helpers/table";

test("two writers collide and overwrite is explicit", async ({ browser }) => {
  const ownerContext = await authenticatedContext(browser, "owner@example-school.k12.tr");
  const adminContext = await authenticatedContext(browser, "admin@example-school.k12.tr");
  const owner = await ownerContext.newPage();
  const admin = await adminContext.newPage();
  const assignmentsResponse = await owner.request.get("/api/my-assignments");
  expect(assignmentsResponse.ok()).toBeTruthy();
  const assignment = (await assignmentsResponse.json())[0] as { class_id: number };
  const gridResponse = await owner.request.get(
    `/api/classes/${assignment.class_id}/grid?subject=english&locale=en`,
  );
  const grid = (await gridResponse.json()) as {
    rows: Array<{ student_id: number; cells: Record<string, { value: number | null }> }>;
    columns: Array<{ id: number }>;
  };
  const cellId = `cell-${grid.rows[0].student_id}-${grid.columns[0].id}`;
  const currentValue = grid.rows[0].cells[String(grid.columns[0].id)]?.value ?? 0;
  const ownerValue = currentValue === 85 ? 86 : 85;
  const adminValue = currentValue === 90 ? 91 : 90;
  const route = `/classes/${assignment.class_id}/english`;

  await owner.goto(route);
  await admin.goto(route);
  await expectFocusedTable(owner.getByTestId("grade-grid-surface"));
  const ownerCell = owner.getByTestId(cellId).getByRole("textbox");
  const adminCell = admin.getByTestId(cellId).getByRole("textbox");
  await ownerCell.fill(String(ownerValue));
  await adminCell.fill(String(adminValue));
  await admin.getByTestId("save-grid").click();
  const ownershipWarning = admin.getByRole("dialog");
  await expect(ownershipWarning).toBeVisible();
  // Matched by test id, not by label: the assertion is about the guard existing,
  // and it should survive rewording the button.
  await ownershipWarning.getByTestId("confirm-ownership").click();
  await expect(ownershipWarning).toBeHidden();
  await expect(adminCell).toHaveValue(String(adminValue));
  await owner.getByTestId("save-grid").click();
  const dialog = owner.getByRole("dialog");
  await expect(dialog).toContainText(String(adminValue));
  await expect(dialog).toContainText("E2E Admin");
  await dialog.getByTestId("confirm-overwrite").click();
  await expect(dialog).toBeHidden();
  await expect(ownerCell).toHaveValue(String(ownerValue));

  await ownerContext.close();
  await adminContext.close();
});
