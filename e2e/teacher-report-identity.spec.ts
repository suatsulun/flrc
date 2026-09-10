import { expect, test } from "@playwright/test";
import { authenticatedContext } from "./helpers/auth";
import { adminOrigin } from "./helpers/origins";

// Synthetic one-pixel PNG. The backend validates and canonicalizes it.
const signature = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);

test("admin persists a teacher report name and uploads, replaces and removes a signature", async ({
  browser,
}) => {
  const context = await authenticatedContext(browser, "admin@example-school.k12.tr");
  const page = await context.newPage();
  await page.goto(`${adminOrigin}/admin/users`);
  const row = page.getByRole("row").filter({ hasText: "owner@example-school.k12.tr" });
  await row.getByRole("button", { name: "Report name & signature" }).click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Name on report cards", { exact: true })
    .fill("Synthetic Printed Teacher");
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Save", exact: true })).toBeEnabled();
  const input = dialog.getByLabel("Upload or replace signature", { exact: true });
  await input.setInputFiles({ name: "signature.png", mimeType: "image/png", buffer: signature });
  const image = dialog.getByRole("img", { name: "Signature for E2E Owner" });
  await expect(image).toBeVisible();
  await expect(image).toHaveJSProperty("naturalWidth", 1);
  await page.setViewportSize({ width: 390, height: 667 });
  const bounds = await dialog.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.y).toBeGreaterThanOrEqual(0);
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(667);
  const originalUrl = await image.getAttribute("src");
  await input.setInputFiles({
    name: "invalid.png",
    mimeType: "image/png",
    buffer: Buffer.from("invalid"),
  });
  await expect(dialog.getByRole("alert")).toContainText("Choose a valid");
  await expect(image).toHaveAttribute("src", originalUrl!);
  // Upload the valid PNG again to prove replacement after a failed attempt works.
  await input.setInputFiles({ name: "replacement.png", mimeType: "image/png", buffer: signature });
  await expect(dialog.getByRole("alert")).toBeHidden();
  await expect(input).toBeEnabled();
  await dialog.getByRole("button", { name: "Close", exact: true }).last().click();
  await page.reload();
  await row.getByRole("button", { name: "Report name & signature" }).click();
  await expect(dialog.getByLabel("Name on report cards", { exact: true })).toHaveValue(
    "Synthetic Printed Teacher",
  );
  await expect(image).toBeVisible();
  await dialog.getByRole("button", { name: "Remove signature" }).click();
  await expect(image).toBeHidden();
  await expect(dialog.getByText(/No signature uploaded/)).toBeVisible();
  await dialog.getByLabel("Name on report cards", { exact: true }).fill("");
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Save", exact: true })).toBeEnabled();
  await context.close();
});
